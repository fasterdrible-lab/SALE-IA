"""Bloco 4 / Tarefa 4.3 de docs/tasks-sales-reasoning-engine-completo.md
— extrai hipóteses de motivação de compra reais da conversa
(transcrição + histórico) via IA, alimentando o campo
`buyer_motivation` do SalesReasoningEngine (Fase 7) com dado real em
vez de sempre `None`.

**Nunca reimplementa a validação nem a leitura da motivação
predominante** — toda hipótese passa por `agent/
buyer_motivation_rules.py::validar_hipoteses_motivacao()`/
`motivacao_dominante()` (Fase 5.1), que já garantem por construção o
vocabulário fechado de 12 motivadores e a exigência de evidência real.

**Regra arquitetural herdada, garantida por construção**: "DISC nunca
deverá ser tratado como motivação" — este módulo, assim como `agent/
buyer_motivation_rules.py`, nunca importa nem lê nenhum campo
relacionado a DISC (só transcrição/histórico da conversa entram,
nenhum perfil comportamental).

**Guarda automática, nunca confia só no texto do prompt**: toda
citação em `evidence` é checada literalmente contra o texto da
conversa recebida (substring) — quotes fabricadas são removidas da
lista antes da validação; se a hipótese ficar sem nenhuma citação real,
ela é descartada inteira (mesma regra de `_validar_hipotese`: `evidence`
nunca pode ficar vazia). Mesmo princípio de honestidade de `agent/
spin_extractor.py` (Tarefa 4.1) e `agent/behavioral_signal_
extractor.py` (Tarefa 4.2)."""

import json
from pathlib import Path
from typing import Optional

from agent.buyer_motivation_rules import MOTIVATION_TIPOS, motivacao_dominante
from agent.multiagente.claude_fallback import chamar_ia_com_fallback_claude
from api import ai_features

_PROMPT_PATH = Path(__file__).parent / "prompt_templates" / "buyer_motivation_extractor.txt"

_SYSTEM_PROMPT = (
    "Você identifica hipóteses de motivação de compra em conversas de "
    "venda reais. Responda SEMPRE em JSON válido, sem texto antes ou "
    "depois."
)


def _hipotese_extraida_valida(hipotese: dict, texto_completo: str) -> Optional[dict]:
    """Filtra as citações fabricadas de `evidence` e revalida a
    hipótese resultante. Retorna `None` quando a hipótese não pode ser
    aproveitada (motivação fora do vocabulário, confidence inválida,
    ou nenhuma citação real sobrevive ao filtro)."""
    if not isinstance(hipotese, dict):
        return None

    motivation = hipotese.get("motivation")
    if motivation not in MOTIVATION_TIPOS:
        return None

    try:
        confidence = float(hipotese.get("confidence"))
    except (TypeError, ValueError):
        return None
    if not (0.0 <= confidence <= 1.0):
        return None

    evidence_bruta = hipotese.get("evidence")
    if not isinstance(evidence_bruta, list):
        return None
    # Guarda literal — só mantém citações que existem de verdade na
    # conversa recebida, nunca uma que "parece" real.
    evidence_real = [q for q in evidence_bruta if (q or "").strip() and q.strip() in texto_completo]
    if not evidence_real:
        return None

    return {"motivation": motivation, "confidence": confidence, "evidence": evidence_real}


async def extrair_buyer_motivation_async(
    transcricao_parcial: str,
    historico: str,
    usuario_id: Optional[str] = None,
    meeting_id: Optional[str] = None,
) -> Optional[dict]:
    """Extrai hipóteses de motivação de compra reais da conversa e
    retorna a motivação predominante (`motivacao_dominante()`, Fase
    5.1) — `None` quando nenhuma hipótese sobreviveu à validação (sem
    sinal claro na conversa, motivação fabricada, ou citação
    inventada). Propaga exceção de falha real de IA (4 provedores +
    fallback Claude esgotados) — o chamador decide tratar como melhor
    esforço (ver `agent/multiagente/orquestrador.py`)."""
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
        feature=ai_features.BUYER_MOTIVATION_EXTRACAO,
        meeting_id=meeting_id,
    )

    hipoteses_brutas = (resposta or {}).get("hipoteses") or []
    texto_completo = f"{historico or ''}\n{transcricao_parcial or ''}"

    hipoteses_validas = []
    for hipotese in hipoteses_brutas:
        valida = _hipotese_extraida_valida(hipotese, texto_completo)
        if valida is not None:
            hipoteses_validas.append(valida)

    return motivacao_dominante(hipoteses_validas)
