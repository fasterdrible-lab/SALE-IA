"""Bloco 5 / Tarefa 5.1 de docs/tasks-sales-reasoning-engine-completo.md
— extrai observações reais de estilo do vendedor a partir da
transcrição completa de uma reunião já encerrada, restritas aos 12
campos canônicos de `agent/seller_dna_rules.py::SELLER_DNA_CAMPOS`
(Fase 15.1).

**Nunca reimplementa a validação do SellerDNA** — toda observação passa
por `validar_sem_alegacao_de_eficacia()` (Fase 15.2) antes de ser
aceita: SellerDNA registra comportamento, nunca eficácia.

**Guarda automática, nunca confia só no texto do prompt**: todo
`evidence_quote` é checado literalmente contra a transcrição recebida
(substring) — quote fabricada descarta só aquela observação, nunca a
resposta inteira. Mesmo princípio de honestidade de `agent/
buyer_motivation_extractor.py`/`agent/spin_extractor.py` (Bloco 4).

**Diferente dos extratores do Bloco 4**: aqueles rodam por FRAGMENTO,
durante o ciclo de `/tempo-real` (gated por Shadow Mode/Piloto). Este
roda uma vez por REUNIÃO ENCERRADA, no mesmo hook pós-reunião onde a
Sales Memory já é extraída automaticamente (`agent/
knowledge_extractor.py::extrair_e_salvar_memorias`) — é a única forma
de acumular reuniões reais rumo ao mínimo de 10 exigido por
`construir_seller_dna()` antes do perfil poder ser montado."""

import logging
from pathlib import Path
from typing import Optional

from agent.multiagente.claude_fallback import chamar_ia_com_fallback_claude
from agent.seller_dna_rules import SELLER_DNA_CAMPOS, validar_sem_alegacao_de_eficacia
from api import ai_features

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompt_templates" / "seller_dna_extractor.txt"

_SYSTEM_PROMPT = (
    "Você identifica padrões de estilo do vendedor em transcrições completas de "
    "reuniões de vendas reais já encerradas. Responda SEMPRE em JSON válido, sem "
    "texto antes ou depois."
)


def _observacao_extraida_valida(observacao: dict, texto_completo: str) -> Optional[dict]:
    """Valida uma observação bruta da IA — descarta (retorna `None`)
    quando o campo não é canônico, o `evidence_quote` não existe
    literalmente na transcrição, ou o valor contém alegação de
    eficácia (Fase 15.2). Uma observação inválida nunca derruba as
    outras da mesma resposta."""
    if not isinstance(observacao, dict):
        return None

    campo = observacao.get("campo")
    if campo not in SELLER_DNA_CAMPOS:
        return None

    valor = (observacao.get("valor") or "").strip()
    if not valor:
        return None

    evidence_quote = (observacao.get("evidence_quote") or "").strip()
    if not evidence_quote or evidence_quote not in texto_completo:
        return None

    try:
        validar_sem_alegacao_de_eficacia(campo, valor)
    except ValueError:
        return None

    return {"campo": campo, "valor": valor, "evidence_quote": evidence_quote}


async def extrair_observacoes_seller_dna_async(
    transcricao: str,
    seller_id: str,
    meeting_id: Optional[str] = None,
    usuario_id: Optional[str] = None,
) -> list:
    """Extrai observações de estilo reais do vendedor a partir da
    transcrição COMPLETA de uma reunião encerrada. Retorna sempre uma
    lista (nunca `None` em sucesso, mesmo vazia quando nenhum padrão
    claro foi identificado) — lista vazia é informação real, mesma
    disciplina dos extratores do Bloco 4. Propaga exceção de falha real
    de IA (4 provedores + fallback Claude esgotados) — o chamador
    decide tratar como melhor esforço."""
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    prompt = template.replace("{transcricao}", transcricao or "")

    resposta = await chamar_ia_com_fallback_claude(
        _SYSTEM_PROMPT,
        prompt,
        usuario_id,
        feature=ai_features.SELLER_DNA_EXTRACAO,
        meeting_id=meeting_id,
    )

    observacoes_brutas = (resposta or {}).get("observacoes") or []
    texto_completo = transcricao or ""

    observacoes_validas = []
    for observacao in observacoes_brutas:
        valida = _observacao_extraida_valida(observacao, texto_completo)
        if valida is not None:
            observacoes_validas.append(valida)

    return observacoes_validas


async def extrair_e_salvar_seller_dna_observacoes(
    resultado: dict,
    transcricao: str,
    meeting_id: Optional[str] = None,
) -> list:
    """Pipeline completo pós-reunião: resolve o vendedor dono da
    reunião, extrai observações reais via IA e persiste no banco.
    Projetado para `background_tasks.add_task` (mesmo padrão de `agent/
    knowledge_extractor.py::extrair_e_salvar_memorias`) — melhor
    esforço absoluto, nunca propaga exceção (uma falha aqui não pode
    derrubar o pipeline pós-reunião).

    `resultado` é aceito só para manter a mesma assinatura do resto do
    pipeline pós-reunião (`extrair_e_salvar_memorias`/
    `gerar_e_salvar_playbook`) — este módulo não lê nada dele, só a
    transcrição bruta importa aqui.

    **Sem MeetingMemory (`usuario_id`) resolvível para o `meeting_id`,
    nenhuma observação é salva** — atribuir uma observação de estilo a
    um vendedor errado seria pior que não ter o dado. Reuniões sem dono
    (ex.: recapitulação manual sem `meeting_id` de uma sessão real ao
    vivo) simplesmente não alimentam o SellerDNA ainda."""
    if not meeting_id:
        return []

    try:
        from api.database import criar_seller_dna_observacao, obter_meeting_memory

        memoria = obter_meeting_memory(meeting_id)
        seller_id = (memoria or {}).get("usuario_id")
        if not seller_id:
            logger.debug(
                "[SellerDNA] Reunião %s sem usuario_id resolvido — observações não atribuídas.", meeting_id,
            )
            return []

        observacoes = await extrair_observacoes_seller_dna_async(
            transcricao, seller_id, meeting_id=meeting_id, usuario_id=seller_id,
        )
        if not observacoes:
            logger.info("[SellerDNA] Nenhuma observação extraída para a reunião %s.", meeting_id)
            return []

        salvas = []
        for observacao in observacoes:
            try:
                salva = criar_seller_dna_observacao(
                    seller_id=seller_id,
                    meeting_id=meeting_id,
                    campo=observacao["campo"],
                    valor=observacao["valor"],
                    evidence_quote=observacao["evidence_quote"],
                )
                salvas.append(salva)
            except ValueError as e:
                logger.warning("[SellerDNA] Observação inválida descartada (reunião %s): %s", meeting_id, e)

        logger.info(
            "[SellerDNA] %d observação(ões) salva(s) para o vendedor %s (reunião %s).",
            len(salvas), seller_id, meeting_id,
        )
        return salvas
    except Exception as e:
        logger.error("[SellerDNA] Erro no pipeline de extração (reunião %s): %s", meeting_id, e)
        return []
