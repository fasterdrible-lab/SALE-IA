# -*- coding: utf-8 -*-
"""
SALEIA — agent/pattern_discovery_rules.py

Descoberta de Padrões (FASE 12 / TAREFA 12.2 do "PROMPT MESTRE —
SALE-IA V2"), fecha a Fase 12 (Collective Sales Intelligence). Função
pura (sem IA/banco) — reaproveita as primitivas de `win_loss_rules.py`
(Fase 8: IC de Wilson, amostra mínima) em vez de duplicar estatística,
mesmo princípio já usado em `seller_benchmark_rules.py` (Tarefa 12.1).

Objetivo literal do prompt mestre: testar uma hipótese de comportamento
(ex.: "vendedores de alta conversão exploram implicação antes de
apresentar solução") comparando a taxa do comportamento entre um
"top group" e um "control group", mostrando `sample`/`top group`/
`control group`/`difference`/`confidence`.

**Reuso, não reinvenção**: a comparação de taxa entre 2 grupos com IC
de Wilson já existe em `win_loss_rules.comparar_por_variavel_
categorica()` (Fase 8) para `status` won/lost por categoria — aqui o
"desfecho" é o comportamento observado (`exhibited`) em vez de
won/lost, e a "categoria" é o grupo (`top`/`control`) em vez de
segmento/estratégia. Mesma função, reaproveitada sem alteração.

**Significância sem scipy — mesma disciplina honesta e
auto-calibrada de `seasonality_rules.py` (Fase 9)**: em vez de um
teste de hipótese formal (qui-quadrado exigiria scipy, dependência
nova), a diferença só é reportada como `diferenca_significativa` quando
os 2 grupos têm amostra suficiente **e** os intervalos de confiança de
Wilson dos 2 grupos não se sobrepõem — sinal honesto, não um p-valor.

**Regra científica herdada das Fases 8-9 — nunca causa, sempre
associação**: única string de texto livre vem de `TEMPLATE_PADRAO_
DESCOBERTO`/`TEMPLATE_PADRAO_SEM_SINAL` (templates fixos), guardado
por `GuardaContraCausalidadeTest`.

**Quem monta as observações e o que é "exhibited"**: cada observação é
`{"group": "top"|"control", "exhibited": bool}` — `group` já
classificado pelo chamador (quem é "alta conversão" é definição de
negócio, não decidida aqui — mesmo padrão de `seller_tier` em
`seller_benchmark_rules.py`), `exhibited` já classificado pelo
chamador (se o comportamento da hipótese ocorreu naquela
reunião/vendedor — este módulo nunca extrai comportamento de
transcrição livre). A `hipotese` (texto) é só uma etiqueta de
rastreabilidade no resultado, nunca interpretada/validada pelo módulo.
"""

from typing import Optional

from agent.win_loss_rules import (
    AMOSTRA_MINIMA_PADRAO,
    amostra_suficiente,
    comparar_por_variavel_categorica,
)

GRUPOS_VALIDOS = ("top", "control")

TEMPLATE_PADRAO_DESCOBERTO = (
    "{hipotese!r} está associada a uma diferença de {diferenca:+.0%} "
    "entre o grupo top (n={n_top}) e o grupo controle (n={n_control}) "
    "nesta amostra, com intervalos de confiança de {confianca:.0%} que "
    "não se sobrepõem — associação observada nesta amostra, nunca "
    "confirmação de mecanismo."
)
TEMPLATE_PADRAO_SEM_SINAL = (
    "{hipotese!r}: sem evidência suficiente nesta amostra para afirmar "
    "qualquer associação (amostra insuficiente ou intervalos de "
    "confiança sobrepostos)."
)


def descobrir_padrao(
    observacoes: list,
    hipotese: str = "",
    minimo_amostra: int = AMOSTRA_MINIMA_PADRAO,
    confianca: float = 0.95,
) -> dict:
    """Testa uma hipótese de comportamento comparando a taxa de
    `exhibited=True` entre o grupo `top` e o grupo `control`.

    `observacoes`: lista de dicts `{"group": "top"|"control",
    "exhibited": bool}` — reaproveita `win_loss_rules.comparar_por_
    variavel_categorica()` tratando `exhibited` como o desfecho
    (equivalente a won/lost) e `group` como a categoria.

    Retorna `{"hipotese", "sample", "top_group", "control_group",
    "difference", "confidence", "diferenca_significativa",
    "afirmacao"}`. `difference` é `None` quando falta taxa de algum
    dos 2 grupos. `diferenca_significativa` só é `True` quando os 2
    grupos têm amostra suficiente e os ICs de Wilson não se sobrepõem
    — nunca por omissão.
    """
    for obs in observacoes:
        if obs.get("group") not in GRUPOS_VALIDOS:
            raise ValueError(f"group inválido: {obs.get('group')!r} (esperado um de {GRUPOS_VALIDOS})")
        if not isinstance(obs.get("exhibited"), bool):
            raise ValueError(f"exhibited inválido: {obs.get('exhibited')!r} (esperado bool)")

    linhas = [{"group": obs["group"], "status": "won" if obs["exhibited"] else "lost"} for obs in observacoes]
    comparacao = comparar_por_variavel_categorica(linhas, campo="group", minimo_amostra=minimo_amostra, confianca=confianca)
    grupos = comparacao["grupos"]

    top_group = grupos.get("top", {"won": 0, "lost": 0, "total": 0, "taxa_conversao": None, "amostra_suficiente": False, "intervalo_confianca": None})
    control_group = grupos.get("control", {"won": 0, "lost": 0, "total": 0, "taxa_conversao": None, "amostra_suficiente": False, "intervalo_confianca": None})

    taxa_top = top_group["taxa_conversao"]
    taxa_control = control_group["taxa_conversao"]
    difference: Optional[float] = (taxa_top - taxa_control) if (taxa_top is not None and taxa_control is not None) else None

    ic_nao_sobrepoe = False
    if top_group["intervalo_confianca"] and control_group["intervalo_confianca"]:
        (top_inf, top_sup) = top_group["intervalo_confianca"]
        (ctrl_inf, ctrl_sup) = control_group["intervalo_confianca"]
        ic_nao_sobrepoe = (top_inf > ctrl_sup) or (ctrl_inf > top_sup)

    diferenca_significativa = bool(
        top_group["amostra_suficiente"] and control_group["amostra_suficiente"] and ic_nao_sobrepoe
    )

    if diferenca_significativa:
        afirmacao = TEMPLATE_PADRAO_DESCOBERTO.format(
            hipotese=hipotese, diferenca=difference, n_top=top_group["total"], n_control=control_group["total"], confianca=confianca,
        )
    else:
        afirmacao = TEMPLATE_PADRAO_SEM_SINAL.format(hipotese=hipotese)

    return {
        "hipotese": hipotese,
        "sample": len(observacoes),
        "top_group": top_group,
        "control_group": control_group,
        "difference": difference,
        "confidence": confianca,
        "diferenca_significativa": diferenca_significativa,
        "afirmacao": afirmacao,
    }
