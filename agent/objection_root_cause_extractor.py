"""Bloco 4 / Tarefa 4.4 de docs/tasks-sales-reasoning-engine-completo.md
— investiga a causa raiz de uma objeção já classificada (Tarefa 1.2),
usando a conversa completa como contexto.

Regra central do prompt mestre (Fase 6.1, `agent/objection_rules.py`):
"Está caro." nunca pode virar automaticamente `root_cause = PRICE`
com a mesma evidência do que foi falado — isso é espelhamento, não
investigação. `agent/objection_rules.py::precisa_investigar()` já
garante isso estruturalmente (hipótese que repete categoria+evidência
sempre marca `precisa_investigar=True`, nunca falso negativo). Este
módulo adiciona uma **segunda guarda, defensiva**: nunca confia só no
texto do prompt pedindo pra IA não espelhar — descarta explicitamente
qualquer resposta que caia nesse padrão antes mesmo de persistir,
tratando como "sem hipótese real" (`None`), nunca como uma hipótese
fraca.
"""

import json
from pathlib import Path
from typing import Optional

from agent.multiagente.claude_fallback import chamar_ia_com_fallback_claude
from api import ai_features

_PROMPT_PATH = Path(__file__).parent / "prompt_templates" / "objecao_causa_raiz.txt"

_SYSTEM_PROMPT = (
    "Você investiga a causa raiz de objeções de venda a partir da "
    "conversa real. Responda SEMPRE em JSON válido, sem texto antes "
    "ou depois."
)


async def investigar_causa_raiz_async(
    objection_spoken: dict,
    transcricao_parcial: str,
    historico: str,
    usuario_id: Optional[str] = None,
    meeting_id: Optional[str] = None,
) -> Optional[dict]:
    """Investiga a causa raiz de `objection_spoken` (já montado por
    `agent/objecao_detectada_para_objection_rules.py::montar_
    objection_spoken()`) usando a conversa completa. Retorna um
    `root_cause_hypothesis` pronto pro formato de `agent/
    objection_rules.py`, ou `None` quando a IA não encontrar sinal
    real, quando a resposta cair no padrão proibido de espelhamento
    (guarda defensiva, nunca confia só no prompt), ou em qualquer
    resposta malformada — nunca fabrica hipótese."""
    categoria = objection_spoken.get("category")
    objecao_texto = objection_spoken.get("evidence_quote")
    if not categoria or not (objecao_texto or "").strip():
        return None

    template = _PROMPT_PATH.read_text(encoding="utf-8")
    prompt = (
        template
        .replace("{categoria}", categoria)
        .replace("{objecao_texto}", objecao_texto)
        .replace("{historico}", historico or "")
        .replace("{transcricao_parcial}", transcricao_parcial or "")
    )

    resposta = await chamar_ia_com_fallback_claude(
        _SYSTEM_PROMPT,
        prompt,
        usuario_id,
        feature=ai_features.OBJECTION_CAUSA_RAIZ_INVESTIGACAO,
        meeting_id=meeting_id,
    )

    hypothesis = (resposta or {}).get("hypothesis")
    evidence_quote = (resposta or {}).get("evidence_quote")
    confidence = (resposta or {}).get("confidence")

    if not (hypothesis or "").strip() or not (evidence_quote or "").strip():
        return None
    try:
        confidence_valor = float(confidence)
    except (TypeError, ValueError):
        return None
    if not (0.0 <= confidence_valor <= 1.0):
        return None

    # Guarda defensiva — nunca confia só no texto do prompt pedindo pra
    # IA não espelhar a objeção. Mesmo padrão proibido que agent/
    # objection_rules.py::precisa_investigar() detecta depois, mas
    # descartado aqui pra nunca nem persistir uma "hipótese" que é só
    # a objeção repetida.
    if hypothesis.strip().upper() == categoria.strip().upper():
        return None
    if evidence_quote.strip() == objecao_texto.strip():
        return None

    return {
        "hypothesis": hypothesis,
        "evidence_quote": evidence_quote,
        "confidence": confidence_valor,
    }
