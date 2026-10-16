"""Relatório pós-reunião automático (V.1.4.185). Regras em
`agent/relatorio_automatico_rules.py`.

Roda no laço de métricas (`api/main.py::_loop_metricas`, a cada ~2 min):
acha sessões cuja reunião acabou, reserva uma por vez no banco (os 2
workers não geram em dobro), gera o mesmo relatório de Dashboard →
Relatórios a partir da transcrição completa (`meeting_memory`) e roda o
pipeline pós-reunião: cliente/oportunidade (B7), memórias comerciais,
playbook, indexação semântica e Seller DNA.

Estado em `sessoes.relatorio_status` / `relatorio_em` / `relatorio_detalhe`.
"""
from __future__ import annotations

import logging
from datetime import datetime

from agent.relatorio_automatico_rules import (
    STATUS_ERRO,
    STATUS_GERANDO,
    STATUS_OK,
    STATUS_PULADO,
    habilitado,
    sessao_pronta,
    titulo_da_reuniao,
    transcricao_para_relatorio,
    vale_gerar,
)

logger = logging.getLogger("saleia.relatorio_automatico")


def gerar_relatorio(transcricao: str, titulo: str, meeting_id: str, usuario_id: str | None,
                    data: str | None = None) -> dict:
    """Mesmo relatório de `POST /recapitulacao-manual` + pipeline pós-reunião,
    executado na thread de quem chamou (aqui não há BackgroundTasks)."""
    from api import main as m

    conteudo = f"REUNIÃO: {titulo}\nDATA: {data or 'não informada'}\n\nTRANSCRIÇÃO:\n{transcricao}"
    resultado = {
        "titulo": titulo,
        "data": data or datetime.now().isoformat(),
        "recapitulacao": m.chamar_gpt(m.PROMPT_RECAPITULACAO, conteudo,
                                      feature=m.ai_features.REPORT_RECAPITULACAO, meeting_id=meeting_id),
        "diagnostico_financeiro": m.chamar_gpt(m.PROMPT_DIAGNOSTICO_FINANCEIRO, transcricao,
                                               feature=m.ai_features.REPORT_DIAGNOSTICO_FINANCEIRO, meeting_id=meeting_id),
        "perfil_disc": m.chamar_gpt(m.PROMPT_PERFIL_DISC, transcricao,
                                    feature=m.ai_features.REPORT_PERFIL_DISC, meeting_id=meeting_id),
        "gerado_em": datetime.now().isoformat(),
        "origem": "automatico",
    }
    m.db_salvar(meeting_id=meeting_id, nome_reuniao=titulo, dados=resultado)  # Dashboard → Reuniões

    etapas = []

    def _etapa(nome, funcao, *args):
        try:
            funcao(*args)
            etapas.append(nome)
        except Exception as exc:  # uma etapa nunca derruba as outras
            logger.warning("[RelatorioAutomatico] %s falhou em %s: %s", nome, meeting_id, exc)

    _etapa("astrologia", m._processar_perfil_astrologico, resultado, meeting_id)
    from agent.auto_opportunity_rules import processar_cliente_e_oportunidade
    _etapa("cliente_oportunidade", processar_cliente_e_oportunidade, resultado, meeting_id, titulo, usuario_id)
    from agent.knowledge_extractor import extrair_e_salvar_memorias
    _etapa("memorias", extrair_e_salvar_memorias, resultado, transcricao, meeting_id)
    from agent.playbook_generator import _eh_reuniao_de_sucesso, gerar_e_salvar_playbook
    try:
        if _eh_reuniao_de_sucesso(resultado, meeting_id):
            _etapa("playbook", gerar_e_salvar_playbook, resultado, transcricao, meeting_id)
    except Exception as exc:
        logger.warning("[RelatorioAutomatico] playbook (checagem) falhou em %s: %s", meeting_id, exc)
    from agent.semantic_search import indexar_relatorio, indexar_transcricao
    _etapa("indexar_relatorio", indexar_relatorio, meeting_id, titulo, resultado)
    _etapa("indexar_transcricao", indexar_transcricao, meeting_id, titulo, transcricao)
    if m._seller_dna_observacao_habilitado():
        from agent.seller_dna_extractor import extrair_e_salvar_seller_dna_observacoes
        _etapa("seller_dna", extrair_e_salvar_seller_dna_observacoes, resultado, transcricao, meeting_id)
    resultado["_etapas_ok"] = etapas
    return resultado


# ── Fila no banco (tabela sessoes) ─────────────────────────────────────

def _conn():
    from agent.sessao_manager import _get_conn
    return _get_conn()


def _reservar(sessao_id: int) -> bool:
    """Só 1 worker leva a sessão. 'gerando' há mais de 30 min (restart no
    meio) pode ser retomada."""
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE sessoes SET relatorio_status = %s, relatorio_em = NOW(), updated_at = updated_at
                   WHERE id = %s AND (relatorio_status IS NULL
                        OR (relatorio_status = %s AND relatorio_em < NOW() - INTERVAL 30 MINUTE))""",
                (STATUS_GERANDO, sessao_id, STATUS_GERANDO),
            )
            ganhou = cur.rowcount == 1
        conn.commit()
        return ganhou
    finally:
        conn.close()


def _marcar(sessao_id: int, status: str, detalhe: str = "") -> None:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE sessoes SET relatorio_status = %s, relatorio_detalhe = %s, relatorio_em = NOW(),
                          updated_at = updated_at WHERE id = %s""",
                (status, (detalhe or "")[:200], sessao_id),
            )
        conn.commit()
    finally:
        conn.close()


def _candidatas() -> list[tuple]:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, meeting_id, updated_at, encerrada_em FROM sessoes
                   WHERE relatorio_status IS NULL
                      OR (relatorio_status = %s AND relatorio_em < NOW() - INTERVAL 30 MINUTE)
                   ORDER BY updated_at LIMIT 20""",
                (STATUS_GERANDO,),
            )
            return list(cur.fetchall())
    finally:
        conn.close()


def processar_pendentes(max_por_vez: int = 2, agora: datetime | None = None) -> list[dict]:
    """Uma volta da fila. Retorna o que aconteceu com cada sessão tocada."""
    if not habilitado():
        return []
    from api.database import obter_meeting_memory

    agora = agora or datetime.now()
    feitos: list[dict] = []
    for sessao_id, meeting_id, updated_at, encerrada_em in _candidatas():
        if len(feitos) >= max_por_vez:
            break
        if not sessao_pronta(encerrada_em, updated_at, agora) or not _reservar(sessao_id):
            continue
        registro = {"sessao_id": sessao_id, "meeting_id": meeting_id}
        try:
            memoria = obter_meeting_memory(meeting_id) or {}
            transcricao = memoria.get("transcript_full") or ""
            ok, motivo = vale_gerar(transcricao)
            if not ok:
                _marcar(sessao_id, STATUS_PULADO, motivo)
                registro["status"], registro["detalhe"] = STATUS_PULADO, motivo
            else:
                inicio_iso = memoria.get("created_at")  # ISO em texto (_meeting_memory_to_dict)
                try:
                    inicio = datetime.fromisoformat(inicio_iso) if inicio_iso else None
                except ValueError:
                    inicio = None
                titulo = titulo_da_reuniao(meeting_id, inicio)
                resultado = gerar_relatorio(
                    transcricao_para_relatorio(transcricao), titulo, meeting_id, memoria.get("usuario_id"),
                    data=inicio_iso,
                )
                detalhe = "etapas: " + ", ".join(resultado.get("_etapas_ok") or [])
                _marcar(sessao_id, STATUS_OK, detalhe)
                registro["status"], registro["detalhe"] = STATUS_OK, detalhe
                logger.info("[RelatorioAutomatico] relatório gerado para %s (sessão %s) — %s", meeting_id, sessao_id, detalhe)
        except Exception as exc:
            logger.warning("[RelatorioAutomatico] erro na sessão %s (%s): %s", sessao_id, meeting_id, exc)
            try:
                _marcar(sessao_id, STATUS_ERRO, type(exc).__name__)
            except Exception:
                pass
            registro["status"], registro["detalhe"] = STATUS_ERRO, type(exc).__name__
        feitos.append(registro)
    return feitos
