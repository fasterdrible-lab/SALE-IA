"""Tarefa A5 de docs/tasks-prompt-mestre-v2-restante.md — extrai fatos
MEDDPICC reais da conversa (transcrição + histórico) via IA, alimentando
o campo `meddpicc_state` do SalesReasoningEngine (Fase 7), que até aqui
vinha sempre `None`. Desbloqueia a Tarefa 1.1 de docs/
tasks-sales-reasoning-engine-completo.md **sem mexer no prompt do
Closer** (a razão do bloqueio original: o `maturity_score` do Closer só
tem números, nunca a citação que os sustenta).

Mesmo padrão de `agent/spin_extractor.py` (Bloco 4.1):
- vocabulário fechado dos 8 itens de `meddpicc_rules.MEDDPICC_ITENS`
  (a IA nunca inventa item novo), status só `PARTIAL`/`CONFIRMED` (um
  fato `UNKNOWN` não diz nada);
- **guarda automática, nunca confia só no prompt**: toda
  `evidence_quote` precisa existir literalmente na conversa recebida
  (substring exata) — citação fabricada é descartada;
- **nunca recalcula qualificação**: só produz os fatos; o estado é
  sempre `meddpicc_rules.calcular_qualificacao_meddpicc()` (Fase 4.1).

Além de `item`/`status`/`confidence`/`evidence_quote` (contrato da Fase
4.1), cada fato traz `valor` (resumo curto, ex.: "CFO Marcos") — é o que
a A3 grava na OpportunityMemory (`champion`, `economic_buyer`...).

Kill-switch `MEDDPICC_EXTRACTOR_ENABLED` (default `true`): +1 chamada
de IA por ciclo nos caminhos Shadow/Piloto; `false` no `.env` + restart
desliga sem reverter deploy.
"""

import os
from pathlib import Path
from typing import Optional

from agent.meddpicc_rules import MEDDPICC_ITENS, calcular_qualificacao_meddpicc
from agent.multiagente.claude_fallback import chamar_ia_com_fallback_claude
from api import ai_features

_PROMPT_PATH = Path(__file__).parent / "prompt_templates" / "meddpicc_extractor.txt"

_SYSTEM_PROMPT = (
    "Você extrai fatos de qualificação MEDDPICC de conversas de venda "
    "reais. Responda SEMPRE em JSON válido, sem texto antes ou depois."
)

_STATUS_EXTRAIVEIS = frozenset({"PARTIAL", "CONFIRMED"})


def meddpicc_extractor_ativo() -> bool:
    return os.getenv("MEDDPICC_EXTRACTOR_ENABLED", "true").strip().lower() != "false"


def _fato_extraido_valido(fato, texto_completo: str) -> bool:
    if not isinstance(fato, dict):
        return False
    if fato.get("item") not in MEDDPICC_ITENS:
        return False
    if fato.get("status") not in _STATUS_EXTRAIVEIS:
        return False
    valor = fato.get("valor")
    if not isinstance(valor, str) or not valor.strip():
        return False
    try:
        confidence = float(fato.get("confidence"))
    except (TypeError, ValueError):
        return False
    if not (0.0 <= confidence <= 1.0):
        return False
    evidence_quote = (fato.get("evidence_quote") or "").strip() if isinstance(fato.get("evidence_quote"), str) else ""
    if not evidence_quote:
        return False
    # Guarda literal — a citação precisa existir de verdade na conversa.
    return evidence_quote in texto_completo


async def extrair_fatos_meddpicc_async(
    transcricao_parcial: str,
    historico: str,
    usuario_id: Optional[str] = None,
    meeting_id: Optional[str] = None,
) -> list:
    """Extrai e valida os fatos MEDDPICC da conversa — **sempre uma
    lista** em sucesso (vazia é informação real: nada qualificado
    ainda). Cada fato: `{"item", "status", "valor", "confidence",
    "evidence_quote"}`. Propaga exceção de falha real de IA — o chamador
    trata como melhor esforço (ver `agent/multiagente/orquestrador.py`)."""
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
        feature=ai_features.MEDDPICC_EXTRACAO,
        meeting_id=meeting_id,
    )

    fatos_brutos = (resposta or {}).get("fatos") if isinstance(resposta, dict) else None
    texto_completo = f"{historico or ''}\n{transcricao_parcial or ''}"

    fatos, itens_vistos = [], set()
    for fato in fatos_brutos or []:
        if not _fato_extraido_valido(fato, texto_completo):
            continue
        if fato["item"] in itens_vistos:
            continue  # mesmo item relatado 2x pela IA — mantém a primeira ocorrência
        itens_vistos.add(fato["item"])
        fatos.append({
            "item": fato["item"],
            "status": fato["status"],
            "valor": fato["valor"].strip(),
            "confidence": float(fato["confidence"]),
            "evidence_quote": fato["evidence_quote"].strip(),
        })
    return fatos


def estado_meddpicc(fatos: list) -> dict:
    """Estado dos 8 itens a partir dos fatos já validados — sempre via
    `calcular_qualificacao_meddpicc()` (Fase 4.1), nunca recalculado aqui."""
    return calcular_qualificacao_meddpicc([
        {k: f[k] for k in ("item", "status", "confidence", "evidence_quote")} for f in fatos or []
    ])
