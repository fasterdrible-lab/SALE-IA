# -*- coding: utf-8 -*-
"""
SALEIA — agent/seller_benchmark_rules.py

Benchmark dos Melhores Vendedores (FASE 12 / TAREFA 12.1 do "PROMPT
MESTRE — SALE-IA V2"), início da Fase 12 (Collective Sales
Intelligence). Função pura (sem IA/banco) — reaproveita as primitivas
estatísticas de `win_loss_rules.py` (Fase 8) em vez de duplicá-las,
mesmo princípio já usado em `seasonality_rules.py`/`contextual_
seasonality_rules.py` (Fase 9: "reusar baseline/IC em vez de recalcular
do zero").

Objetivo literal do prompt mestre: comparar o comportamento de
vendedores `top`/`median`/`low` performers — **sem concluir que um
vendedor é melhor só porque recebe leads melhores**. A regra central
("Controlar por segmento/lead source/ticket/produto") é imposta
reaproveitando `win_loss_rules.detectar_simpsons_paradox()`: a
vantagem bruta entre 2 tiers só é reportada como associação real
quando ela se mantém dentro de cada estrato de cada variável de
controle — quando ela se inverte em todos os estratos, é sinalizada
como possível confundimento (mesmo mecanismo/template já usado na
Fase 8, nunca um cálculo novo e paralelo).

**Quem monta as linhas de entrada**: cada linha é uma oportunidade (ou
reunião) já no formato aceito por `win_loss_rules.py` — `status`
(`"won"`/`"lost"`), `seller_tier` (`"top"`/`"median"`/`"low"`, já
classificado pelo chamador a partir de alguma métrica de desempenho
real — este módulo nunca decide sozinho quem é top/median/low) e um
campo por variável de controle já categorizada (`ticket` precisa vir
pré-bucketizado em faixas pelo chamador, ex.: `"baixo"`/`"médio"`/
`"alto"` — comparação categórica exige valores discretos, mesmo
princípio de "quem extrai/classifica o sinal real é integração
futura" já usado em `deal_risk_rules.py` (Fase 4.2) e
`conversation_metrics_rules.py` (Fase 11.1)).
"""

from agent.win_loss_rules import (
    AMOSTRA_MINIMA_PADRAO,
    comparar_por_variavel_categorica,
    detectar_simpsons_paradox,
)

PERFORMANCE_TIERS = ("top", "median", "low")

CONTROL_VARIABLES = ("segment", "lead_source", "ticket", "product")


def comparar_tiers(opportunities: list, minimo_amostra: int = AMOSTRA_MINIMA_PADRAO) -> dict:
    """Taxa de conversão bruta (não controlada) de cada tier presente na
    amostra — reaproveita `win_loss_rules.comparar_por_variavel_
    categorica` direto sobre `seller_tier`, sem nenhum cálculo novo."""
    return comparar_por_variavel_categorica(opportunities, campo="seller_tier", minimo_amostra=minimo_amostra)


def benchmark_controlado(
    opportunities: list,
    tier_a: str = "top",
    tier_b: str = "low",
    campos_controle: tuple = CONTROL_VARIABLES,
) -> dict:
    """Compara `tier_a` × `tier_b` (default: top × low, a comparação
    literal do prompt mestre) e, para cada variável em
    `campos_controle`, checa se a vantagem se mantém dentro de cada
    estrato ou se desaparece/inverte em todos eles — possível
    confundimento ("vendedor X só parece melhor porque recebe leads
    melhores").

    Levanta `ValueError` quando `tier_a`/`tier_b` não estão em
    `PERFORMANCE_TIERS`, ou quando são iguais (nada a comparar).
    """
    if tier_a not in PERFORMANCE_TIERS or tier_b not in PERFORMANCE_TIERS:
        raise ValueError(f"tiers inválidos: {tier_a!r}/{tier_b!r} (esperado um de {PERFORMANCE_TIERS})")
    if tier_a == tier_b:
        raise ValueError("tier_a e tier_b precisam ser diferentes")

    subset = [o for o in opportunities if o.get("seller_tier") in (tier_a, tier_b)]

    controles = {
        campo_controle: detectar_simpsons_paradox(subset, campo="seller_tier", campo_segmento=campo_controle)
        for campo_controle in campos_controle
    }

    return {
        "tier_a": tier_a,
        "tier_b": tier_b,
        "comparacao_bruta": comparar_por_variavel_categorica(subset, campo="seller_tier"),
        "controles": controles,
    }
