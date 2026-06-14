"""
agent/knowledge_extractor.py — Knowledge Extractor (Sales Brain Fase 1 · Tarefa 1.2)

Pipeline pós-reunião: Relatório → IA → Memórias comerciais reutilizáveis.

Fluxo:
    extrair_e_salvar_memorias(relatorio, transcricao, meeting_id)
        ↓ monta contexto compacto do relatório
        ↓ chama IA com prompt knowledge_extraction.txt
        ↓ parseia JSON de memórias
        ↓ valida tipos
        ↓ salva via sales_memory.salvar_memorias_em_lote()
        → retorna lista de IDs criados

Executado como BackgroundTask após geração do relatório — não bloqueia a resposta.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from api.ai_router import chamar_ia
from agent.sales_memory import salvar_memorias_em_lote, MEMORY_TYPES

logger = logging.getLogger("saleia.knowledge_extractor")

_PROMPT_PATH = Path(__file__).parent / "prompt_templates" / "knowledge_extraction.txt"
_PROMPT_TEMPLATE: Optional[str] = None


def _get_prompt() -> str:
    global _PROMPT_TEMPLATE
    if _PROMPT_TEMPLATE is None:
        _PROMPT_TEMPLATE = _PROMPT_PATH.read_text(encoding="utf-8")
    return _PROMPT_TEMPLATE


# ─────────────────────────────────────────────────────────
# MONTAGEM DE CONTEXTO
# ─────────────────────────────────────────────────────────

def _montar_contexto(relatorio: dict, transcricao: str) -> str:
    """
    Constrói um contexto compacto a partir do relatório e da transcrição.
    Limita a transcrição a 6000 chars para não explodir o contexto da IA.
    """
    partes = []

    titulo = relatorio.get("titulo") or relatorio.get("nome_reuniao") or "Reunião"
    partes.append(f"TÍTULO: {titulo}")

    # Recapitulação (dict ou string)
    recap = relatorio.get("recapitulacao") or {}
    if isinstance(recap, str):
        partes.append(f"\nRECAPITULAÇÃO:\n{recap[:1500]}")
    elif isinstance(recap, dict):
        resumo = recap.get("resumo_executivo") or ""
        estrategica = recap.get("recapitulacao_estrategica") or {}
        emocional = recap.get("recapitulacao_emocional") or {}
        proximo = recap.get("proximos_passos") or recap.get("proximo_passo") or ""

        if resumo:
            partes.append(f"\nRESUMO EXECUTIVO: {resumo}")
        if isinstance(estrategica, dict):
            dor = estrategica.get("dor_principal") or ""
            objecoes = estrategica.get("objecoes") or estrategica.get("objecao_principal") or ""
            sinais = estrategica.get("sinais_compra") or ""
            if dor:
                partes.append(f"DOR PRINCIPAL: {dor}")
            if objecoes:
                partes.append(f"OBJEÇÕES: {objecoes}")
            if sinais:
                partes.append(f"SINAIS DE COMPRA: {sinais}")
        if isinstance(emocional, dict):
            estado = emocional.get("estado_emocional") or ""
            motivacao = emocional.get("motivacao_principal") or ""
            if estado:
                partes.append(f"ESTADO EMOCIONAL: {estado}")
            if motivacao:
                partes.append(f"MOTIVAÇÃO PRINCIPAL: {motivacao}")
        if proximo:
            partes.append(f"PRÓXIMOS PASSOS: {proximo if isinstance(proximo, str) else json.dumps(proximo, ensure_ascii=False)[:300]}")

    # Perfil DISC
    disc = relatorio.get("perfil_disc") or {}
    if isinstance(disc, dict):
        perfil = disc.get("perfil_primario") or disc.get("perfil_disc") or ""
        estrategia = disc.get("estrategia_recomendada") or disc.get("estrategia") or ""
        if perfil:
            partes.append(f"\nPERFIL DISC: {perfil}")
        if estrategia:
            partes.append(f"ESTRATÉGIA DISC: {estrategia[:300]}")
    elif isinstance(disc, str):
        partes.append(f"\nPERFIL DISC: {disc[:300]}")

    # Diagnóstico financeiro
    fin = relatorio.get("diagnostico_financeiro") or {}
    if isinstance(fin, dict):
        fat = fin.get("faturamento_mensal") or fin.get("faturamento_estimado") or ""
        inv = fin.get("capacidade_investimento") or fin.get("investimento_estimado") or ""
        prod = fin.get("produto_recomendado") or fin.get("produto_ideal") or ""
        if fat:
            partes.append(f"\nFATURAMENTO: {fat}")
        if inv:
            partes.append(f"CAPACIDADE DE INVESTIMENTO: {inv}")
        if prod:
            partes.append(f"PRODUTO IDEAL: {prod}")
    elif isinstance(fin, str):
        partes.append(f"\nDIAGNÓSTICO FINANCEIRO: {fin[:400]}")

    # Trecho da transcrição (limitado)
    if transcricao:
        trecho = transcricao.strip()[:6000]
        if len(transcricao) > 6000:
            trecho += "\n[... transcrição truncada ...]"
        partes.append(f"\nTRANSCRIÇÃO:\n{trecho}")

    return "\n".join(partes)


# ─────────────────────────────────────────────────────────
# VALIDAÇÃO
# ─────────────────────────────────────────────────────────

def _validar_memoria(mem: dict) -> Optional[dict]:
    """Valida e normaliza um dict de memória. Retorna None se inválido."""
    if not isinstance(mem, dict):
        return None

    memory_type = mem.get("memory_type", "").strip()
    if memory_type not in MEMORY_TYPES:
        logger.debug("[KnowledgeExtractor] Tipo inválido ignorado: %s", memory_type)
        return None

    title = str(mem.get("title") or "").strip()[:255]
    content = str(mem.get("content") or "").strip()

    if not title or not content or len(content) < 20:
        return None

    try:
        confidence = float(mem.get("confidence", 0.75))
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.75

    tags = mem.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    tags = [str(t).strip() for t in tags if t][:10]

    return {
        "memory_type": memory_type,
        "title": title,
        "content": content,
        "confidence": confidence,
        "tags": tags,
    }


# ─────────────────────────────────────────────────────────
# PIPELINE PRINCIPAL
# ─────────────────────────────────────────────────────────

def extrair_memorias(relatorio: dict, transcricao: str) -> list:
    """
    Chama a IA para extrair memórias comerciais do relatório.

    Returns:
        lista de dicts validados, prontos para salvar_memorias_em_lote()
    """
    contexto = _montar_contexto(relatorio, transcricao)
    prompt = _get_prompt().replace("{contexto}", contexto)

    try:
        # chamar_ia retorna dict (json_object) — o prompt pede {"memorias": [...]}
        resposta = chamar_ia(
            system_prompt=prompt,
            user_content="Extraia os aprendizados comerciais desta reunião.",
        )
    except Exception as e:
        logger.error("[KnowledgeExtractor] Erro ao chamar IA: %s", e)
        return []

    # Extrair lista de candidatos do dict retornado
    candidatos = []
    if isinstance(resposta, dict):
        candidatos = resposta.get("memorias", [])
        if not candidatos:
            # Fallback: tenta qualquer chave cujo valor seja uma lista
            for v in resposta.values():
                if isinstance(v, list) and v:
                    candidatos = v
                    break
    elif isinstance(resposta, list):
        candidatos = resposta

    memorias = []
    for c in candidatos:
        validada = _validar_memoria(c)
        if validada:
            memorias.append(validada)

    logger.info("[KnowledgeExtractor] %d memórias extraídas (de %d candidatos)", len(memorias), len(candidatos))
    return memorias


def extrair_e_salvar_memorias(
    relatorio: dict,
    transcricao: str,
    meeting_id: Optional[str] = None,
    organization_id: Optional[str] = None,
) -> list:
    """
    Pipeline completo: extrai memórias via IA e persiste no banco.
    Projetado para execução em background — captura exceções internamente.

    Args:
        relatorio: resultado completo do relatório (dict com recapitulacao, disc, financeiro)
        transcricao: transcrição bruta da reunião
        meeting_id: id da reunião de origem (rastreabilidade)
        organization_id: tenant (futuro uso multi-tenant)

    Returns:
        lista de UUIDs das memórias criadas
    """
    try:
        memorias = extrair_memorias(relatorio, transcricao)
        if not memorias:
            logger.info("[KnowledgeExtractor] Nenhuma memória extraída para reunião %s", meeting_id)
            return []

        # Injeta rastreabilidade
        for mem in memorias:
            mem["source_meeting_id"] = meeting_id
            mem["organization_id"] = organization_id

        ids = salvar_memorias_em_lote(memorias)
        logger.info(
            "[KnowledgeExtractor] ✅ %d memórias salvas para reunião %s: %s",
            len(ids), meeting_id, ids,
        )
        return ids

    except Exception as e:
        logger.error("[KnowledgeExtractor] Erro no pipeline de extração (reunião %s): %s", meeting_id, e)
        return []
