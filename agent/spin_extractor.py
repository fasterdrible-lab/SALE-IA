"""Bloco 4 / Tarefa 4.1 de docs/tasks-sales-reasoning-engine-completo.md
— extrai fatos SPIN reais da conversa (transcrição + histórico) via
IA, alimentando o campo `spin_state` do SalesReasoningEngine (Fase 7)
com dado real em vez de sempre `None`.

**Nunca recalcula cobertura** — só produz os fatos de entrada
(`{"stage", "campo", "valor", "evidence_quote"}`) que `agent/
spin_coverage_rules.py::calcular_cobertura_spin()` (Fase 3) já sabe
consolidar em known[]/missing[] por estágio. Restrito aos 6 campos
canônicos de `SPIN_CHECKLIST_PADRAO` (Fase 3) — nunca deixa a IA
inventar um vocabulário de campo novo.

**Guarda automática, nunca confia só no texto do prompt**: toda
`evidence_quote` produzida precisa ser um trecho que realmente existe,
literalmente, na conversa recebida (checagem de substring, não "parece
plausível") — mesmo princípio de honestidade de `agent/objection_
root_cause_extractor.py` (Tarefa 4.4)."""

import json
from pathlib import Path
from typing import Optional

from agent.multiagente.claude_fallback import chamar_ia_com_fallback_claude
from agent.spin_coverage_rules import SPIN_CHECKLIST_PADRAO, SPIN_STAGES, calcular_cobertura_spin
from api import ai_features

_PROMPT_PATH = Path(__file__).parent / "prompt_templates" / "spin_extractor.txt"

_SYSTEM_PROMPT = (
    "Você extrai fatos SPIN de conversas de venda reais. Responda "
    "SEMPRE em JSON válido, sem texto antes ou depois."
)

# Campos válidos por estágio — só os 6 canônicos, mesmo vocabulário do
# prompt e de SPIN_CHECKLIST_PADRAO.
_CAMPOS_VALIDOS_POR_STAGE = {
    stage: set(campos) for stage, campos in SPIN_CHECKLIST_PADRAO.items()
}


def _fato_extraido_valido(fato: dict, texto_completo: str) -> bool:
    if not isinstance(fato, dict):
        return False
    stage = fato.get("stage")
    campo = fato.get("campo")
    evidence_quote = (fato.get("evidence_quote") or "").strip()
    valor = (fato.get("valor") or "").strip() if isinstance(fato.get("valor"), str) else fato.get("valor")

    if stage not in SPIN_STAGES:
        return False
    if campo not in _CAMPOS_VALIDOS_POR_STAGE.get(stage, set()):
        return False
    if not valor:
        return False
    if not evidence_quote:
        return False
    # Guarda literal — evidence_quote precisa existir de verdade na
    # conversa recebida, nunca só "parecer" real.
    if evidence_quote not in texto_completo:
        return False
    return True


async def extrair_spin_state_async(
    transcricao_parcial: str,
    historico: str,
    usuario_id: Optional[str] = None,
    meeting_id: Optional[str] = None,
) -> dict:
    """Extrai fatos SPIN reais da conversa e retorna a cobertura já
    calculada (`calcular_cobertura_spin()`, Fase 3) — **sempre um
    dict**, mesmo quando nenhum fato foi encontrado (cobertura vazia é
    informação real: "nada mapeado ainda", não ausência de dado).
    Propaga exceção de falha real de IA (4 provedores + fallback Claude
    esgotados) — o chamador decide tratar como melhor esforço (ver
    `agent/multiagente/orquestrador.py`)."""
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    prompt = (
        template
        .replace("{historico}", historico or "")
        .replace("{transcricao_parcial}", transcricao_parcial or "")
    )

    resposta = await chamar_ia_com_fallback_claude(
        _SYSTEM_PROMPT,
        prompt,
        usuario_id,
        feature=ai_features.SPIN_EXTRACAO_FATOS,
        meeting_id=meeting_id,
    )

    fatos_brutos = (resposta or {}).get("fatos") or []
    texto_completo = f"{historico or ''}\n{transcricao_parcial or ''}"

    fatos_validos = []
    campos_ja_vistos = set()
    for fato in fatos_brutos:
        if not _fato_extraido_valido(fato, texto_completo):
            continue
        chave = (fato["stage"], fato["campo"])
        if chave in campos_ja_vistos:
            continue  # mesmo campo relatado 2x pela IA — mantém só a primeira ocorrência
        campos_ja_vistos.add(chave)
        fatos_validos.append({
            "stage": fato["stage"],
            "campo": fato["campo"],
            "valor": fato["valor"],
            "evidence_quote": fato["evidence_quote"],
        })

    return calcular_cobertura_spin(fatos_validos)
