"""
SALEIA — agent/deal_risk_rules.py

Deal Risk Engine (FASE 4 / TAREFA 4.2 do "PROMPT MESTRE — SALE-IA V2").
Função pura, nenhuma chamada de IA, nenhum acesso a banco — mesmo
padrão de agent/meddpicc_rules.py (Tarefa 4.1), sobre o qual esta tarefa
constrói diretamente.

Regra explícita do prompt mestre — "Não usar LLM para calcular regras
simples": todos os 7 riscos abaixo são derivados deterministicamente de
sinais já estruturados (estado MEDDPICC da Tarefa 4.1 + sinais
observados como "tem próximo passo agendado?"/"quantas objeções de
preço?"/"dias desde a última atividade?") — zero inferência por IA
nesta camada.

Escopo desta tarefa: só o motor de risco em si. De onde exatamente cada
sinal de entrada vem em produção real (ex.: `total_objecoes_preco`
contado a partir de `SalesEvent.event_type == "PRICE_DISCUSSION"`,
`tem_proximo_passo` a partir de `OpportunityMemory.next_steps`) fica
para uma tarefa de integração futura — aqui os sinais chegam já
computados pelo chamador, mesma disciplina de `estado_meddpicc` em
`meddpicc_rules.calcular_qualificacao_meddpicc()`.
"""

from typing import Optional

# Os 7 riscos exemplificados literalmente pelo prompt mestre (TAREFA 4.2).
DEAL_RISK_TIPOS = (
    "NO_ECONOMIC_BUYER",
    "NO_CHAMPION",
    "NO_NEXT_STEP",
    "NO_METRICS",
    "HIGH_PRICE_RESISTANCE",
    "COMPETITOR_ADVANTAGE",
    "STALE_OPPORTUNITY",
)

# Limiares — o prompt mestre não define os números exatos, só pede
# "riscos determinísticos sempre que possível". Decisão desta rodada,
# mesmo tipo de decisão documentada em `question_gap_rules.STAGE_
# PRIORIDADE_PADRAO`/`meddpicc_rules.NIVEL_MINIMO_AVANCADA` — sobrescrevível
# por chamada, não é vocabulário fechado do domínio.
LIMIAR_OBJECOES_PRECO_PADRAO = 3  # 3+ objeções de preço na mesma oportunidade
LIMIAR_DIAS_STALE_PADRAO = 21  # ~3 semanas sem atividade real


def calcular_riscos(
    estado_meddpicc: Optional[dict] = None,
    tem_proximo_passo: bool = True,
    total_objecoes_preco: int = 0,
    competidor_em_vantagem: bool = False,
    dias_desde_ultima_atividade: int = 0,
    limiar_objecoes_preco: int = LIMIAR_OBJECOES_PRECO_PADRAO,
    limiar_dias_stale: int = LIMIAR_DIAS_STALE_PADRAO,
) -> list:
    """Retorna a lista de códigos de risco detectados (subconjunto de
    `DEAL_RISK_TIPOS`, sempre na mesma ordem), a partir de sinais já
    estruturados — nunca calcula nada a partir de transcrição livre.

    - `estado_meddpicc`: saída de `meddpicc_rules.calcular_qualificacao_
      meddpicc()` (Tarefa 4.1) — item ausente/`None` é tratado como
      totalmente `UNKNOWN` (sem cobertura nenhuma).
        - `NO_ECONOMIC_BUYER`: item `economic_buyer` não `CONFIRMED`.
        - `NO_CHAMPION`: item `champion` não `CONFIRMED`.
        - `NO_METRICS`: item `metrics` não `CONFIRMED`.
    - `tem_proximo_passo=False` → `NO_NEXT_STEP`.
    - `total_objecoes_preco >= limiar_objecoes_preco` → `HIGH_PRICE_
      RESISTANCE`.
    - `competidor_em_vantagem=True` → `COMPETITOR_ADVANTAGE` (sinal
      explícito, não deriva do item `competition` do MEDDPICC — aquele
      só indica se o cenário competitivo foi mapeado, não quem está na
      frente).
    - `dias_desde_ultima_atividade >= limiar_dias_stale` → `STALE_
      OPPORTUNITY`."""
    if total_objecoes_preco < 0:
        raise ValueError(f"total_objecoes_preco não pode ser negativo: {total_objecoes_preco!r}")
    if dias_desde_ultima_atividade < 0:
        raise ValueError(f"dias_desde_ultima_atividade não pode ser negativo: {dias_desde_ultima_atividade!r}")

    estado_meddpicc = estado_meddpicc or {}

    def _status_confirmado(item: str) -> bool:
        return estado_meddpicc.get(item, {}).get("status") == "CONFIRMED"

    checagens = {
        "NO_ECONOMIC_BUYER": not _status_confirmado("economic_buyer"),
        "NO_CHAMPION": not _status_confirmado("champion"),
        "NO_NEXT_STEP": not tem_proximo_passo,
        "NO_METRICS": not _status_confirmado("metrics"),
        "HIGH_PRICE_RESISTANCE": total_objecoes_preco >= limiar_objecoes_preco,
        "COMPETITOR_ADVANTAGE": competidor_em_vantagem,
        "STALE_OPPORTUNITY": dias_desde_ultima_atividade >= limiar_dias_stale,
    }

    return [tipo for tipo in DEAL_RISK_TIPOS if checagens[tipo]]
