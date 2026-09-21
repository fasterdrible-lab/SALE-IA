"""Bloco 4 / Tarefa 4.2 de docs/tasks-sales-reasoning-engine-completo.md
— extrai sinais comportamentais reais da conversa (transcrição +
histórico) via IA, alimentando o campo `behavioral_signals` do
SalesReasoningEngine (Fase 7) com dado real em vez de sempre `None`.

**Nunca reimplementa a validação** — só produz a lista de sinais
observados (`{"signal", "evidence_quote"}`), sempre passada por
`agent/behavioral_signal_rules.py::detectar_sinais()` (Fase 5.2) antes
de retornar, que já garante por construção a regra do prompt mestre
("implementar somente sinais observáveis", "evitar alegações
pseudocientíficas") — a descrição canônica sóbria de cada sinal
(`DESCRICOES_SINAIS`) vem de lá, nunca gerada pela IA.

**Guarda automática, nunca confia só no texto do prompt**: toda
`evidence_quote` produzida precisa ser um trecho que realmente existe,
literalmente, na conversa recebida (checagem de substring) — mesmo
princípio de honestidade de `agent/spin_extractor.py` (Tarefa 4.1) e
`agent/objection_root_cause_extractor.py` (Tarefa 4.4)."""

import json
from pathlib import Path
from typing import Optional

from agent.behavioral_signal_rules import BEHAVIORAL_SIGNAL_TIPOS, detectar_sinais
from agent.multiagente.claude_fallback import chamar_ia_com_fallback_claude
from api import ai_features

_PROMPT_PATH = Path(__file__).parent / "prompt_templates" / "behavioral_signal_extractor.txt"

_SYSTEM_PROMPT = (
    "Você identifica sinais comportamentais observáveis em conversas "
    "de venda reais. Responda SEMPRE em JSON válido, sem texto antes "
    "ou depois."
)


def _sinal_extraido_valido(sinal: dict, texto_completo: str) -> bool:
    if not isinstance(sinal, dict):
        return False
    tipo = sinal.get("signal")
    evidence_quote = (sinal.get("evidence_quote") or "").strip()

    if tipo not in BEHAVIORAL_SIGNAL_TIPOS:
        return False
    if not evidence_quote:
        return False
    # Guarda literal — evidence_quote precisa existir de verdade na
    # conversa recebida, nunca só "parecer" real.
    if evidence_quote not in texto_completo:
        return False
    return True


async def extrair_sinais_comportamentais_async(
    transcricao_parcial: str,
    historico: str,
    usuario_id: Optional[str] = None,
    meeting_id: Optional[str] = None,
) -> list:
    """Extrai sinais comportamentais reais da conversa e retorna a
    lista já validada/enriquecida por `detectar_sinais()` (Fase 5.2) —
    **sempre uma lista**, mesmo vazia quando nenhum sinal foi
    encontrado (lista vazia é informação real: "nenhum sinal
    observado ainda", não ausência de dado). Propaga exceção de falha
    real de IA (4 provedores + fallback Claude esgotados) — o chamador
    decide tratar como melhor esforço (ver `agent/multiagente/
    orquestrador.py`)."""
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
        feature=ai_features.BEHAVIORAL_SIGNAL_EXTRACAO,
        meeting_id=meeting_id,
    )

    sinais_brutos = (resposta or {}).get("sinais") or []
    texto_completo = f"{historico or ''}\n{transcricao_parcial or ''}"

    sinais_validos = [
        {"signal": s["signal"], "evidence_quote": s["evidence_quote"]}
        for s in sinais_brutos
        if _sinal_extraido_valido(s, texto_completo)
    ]

    return detectar_sinais(sinais_validos)
