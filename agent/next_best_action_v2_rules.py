# -*- coding: utf-8 -*-
"""
SALEIA — agent/next_best_action_v2_rules.py

Next Best Action V2 (FASE 16 do "PROMPT MESTRE — SALE-IA V2"). Função
pura, nenhuma chamada de IA, nenhum acesso a banco — mesmo padrão dos
demais módulos `*_rules.py` das Fases 1-15. Escopo confirmado com o
usuário: só o contrato de saída + os validadores estruturais de
consistência (sem motor de IA, sem integração com orquestrador) —
mesma disciplina "contrato primeiro" já usada nas Fases 8-15.

A Fase 16 pede uma recomendação que combina 8 dimensões
(`NBA_V2_FONTES_COMBINADAS`: metodologia, contexto, histórico,
sazonalidade, cliente, oportunidade, seller_dna, resultado_observado)
no formato literal do exemplo do prompt mestre (`NBA_V2_OUTPUT_
CAMPOS`: titulo, por_que, spin_gap, meddpicc_gap, historico,
confianca, pergunta, evite).

Regra literal — "a recomendação precisa manter consistência com:
fatos; estágio; políticas; conhecimento disponível" — garantida
estruturalmente por `montar_next_best_action_v2()`, nunca só por
instrução:

- **fatos**: `spin_gap_campo`/`meddpicc_gap_item` precisam ser gaps
  REAIS presentes no `spin_cobertura`/`meddpicc_estado` recebidos
  (Fases 3/4) — nunca inventados.
- **estágio**: `spin_gap_campo` precisa pertencer ao estágio SPIN
  ATUAL (`spin_coverage_rules.estagio_atual()`) — a recomendação não
  pode pular um estágio ainda pendente.
- **políticas**: `bloqueios_politica` (sinais já calculados por
  qualquer motor de política — ex.: `objection_rules.
  precisa_investigar()`, `deal_risk_rules.calcular_riscos()`) precisa
  vir vazio; qualquer bloqueio ativo recusa a recomendação
  (fail-closed, mesmo padrão de `EXPERIMENT_SAFETY_CHECKS`, Fase 14).
- **conhecimento disponível**: `confianca="alta"` exige um
  `historico_insight` real, no formato de
  `sales_science_engine.montar_insight()` (Fase 13) — nunca alta
  confiança sem evidência de histórico por trás.
"""

from typing import Optional

from agent.meddpicc_rules import itens_pendentes
from agent.spin_coverage_rules import estagio_atual

NBA_V2_FONTES_COMBINADAS = (
    "metodologia",
    "contexto",
    "historico",
    "sazonalidade",
    "cliente",
    "oportunidade",
    "seller_dna",
    "resultado_observado",
)

NBA_V2_OUTPUT_CAMPOS = (
    "titulo", "por_que", "spin_gap", "meddpicc_gap", "historico",
    "confianca", "pergunta", "evite",
)

NBA_V2_NIVEIS_CONFIANCA = ("baixa", "media", "alta")

# Mesmo contrato de `sales_science_engine.montar_insight()` (Fase 13) —
# reproduzido aqui só como checklist de presença, sem duplicar a
# validação de valor de cada campo (quem monta o insight já validou
# isso na origem).
_HISTORICO_INSIGHT_CAMPOS_OBRIGATORIOS = (
    "insight", "evidence", "sample", "possible_confounders", "recommended_test",
)


def _validar_spin_gap(spin_cobertura: dict, spin_gap_campo: str) -> None:
    """Regra 'fatos' + 'estágio': `spin_gap_campo` precisa ser um gap
    real do estágio SPIN ATUAL — nunca de um estágio futuro (pular
    etapa) nem de um já coberto (gap inventado)."""
    estagio_esperado = estagio_atual(spin_cobertura)
    missing_do_estagio = spin_cobertura.get(estagio_esperado, {}).get("missing", [])
    if spin_gap_campo not in missing_do_estagio:
        raise ValueError(
            f"spin_gap_campo {spin_gap_campo!r} não é um gap real do estágio SPIN atual "
            f"({estagio_esperado!r}, missing={missing_do_estagio}) — a recomendação não pode "
            "pular um estágio ainda pendente nem inventar um gap que não existe"
        )


def _validar_meddpicc_gap(meddpicc_estado: dict, meddpicc_gap_item: str) -> None:
    """Regra 'fatos': `meddpicc_gap_item` precisa ser um item ainda
    não `CONFIRMED` no estado MEDDPICC recebido."""
    pendentes = itens_pendentes(meddpicc_estado)
    if meddpicc_gap_item not in pendentes:
        raise ValueError(
            f"meddpicc_gap_item {meddpicc_gap_item!r} não é um gap real do meddpicc_estado "
            f"recebido (pendentes={pendentes}) — já está CONFIRMED ou nem existe no vocabulário"
        )


def _validar_historico_insight(historico_insight: dict) -> None:
    """Regra 'conhecimento disponível': um histórico só é aceito
    quando vem no formato de insight com evidência real (mesmo
    contrato de `sales_science_engine.montar_insight()`, Fase 13) —
    nunca uma afirmação de histórico solta, sem lastro."""
    if not isinstance(historico_insight, dict):
        raise ValueError(
            "historico_insight precisa ser um dict no formato de "
            "sales_science_engine.montar_insight()"
        )
    faltando = [
        campo for campo in _HISTORICO_INSIGHT_CAMPOS_OBRIGATORIOS
        if not historico_insight.get(campo) and historico_insight.get(campo) != []
    ]
    if faltando:
        raise ValueError(
            f"historico_insight sem lastro suficiente — faltam campos obrigatórios {faltando} "
            "(mesmo contrato de sales_science_engine.montar_insight())"
        )


def montar_next_best_action_v2(
    titulo: str,
    por_que: str,
    pergunta: str,
    evite: str,
    spin_cobertura: dict,
    spin_gap_campo: str,
    meddpicc_estado: Optional[dict] = None,
    meddpicc_gap_item: Optional[str] = None,
    historico_insight: Optional[dict] = None,
    confianca: str = "media",
    bloqueios_politica: Optional[list] = None,
) -> dict:
    """Monta a recomendação Next Best Action V2 (Fase 16), sempre
    validando as 4 consistências literais do prompt mestre — fatos,
    estágio, políticas, conhecimento disponível — antes de aceitar.

    `spin_cobertura`: resultado de
    `spin_coverage_rules.calcular_cobertura_spin()` (Fase 3).
    `meddpicc_estado`: resultado de
    `meddpicc_rules.calcular_qualificacao_meddpicc()` (Fase 4) —
    obrigatório só quando `meddpicc_gap_item` é informado.
    `historico_insight`: resultado de um wrapper de
    `sales_science_engine` (Fase 13), ou `None` quando não há sinal
    estatístico disponível ainda.
    `bloqueios_politica`: lista (vazia por padrão) de bloqueios já
    decididos por qualquer motor de política (ex.: `objection_rules.
    precisa_investigar()`, `deal_risk_rules.calcular_riscos()`) —
    qualquer item presente recusa a recomendação, fail-closed."""
    for nome, valor in (("titulo", titulo), ("por_que", por_que), ("pergunta", pergunta), ("evite", evite)):
        if not valor or not str(valor).strip():
            raise ValueError(f"{nome} obrigatório e não pode ser vazio")

    if confianca not in NBA_V2_NIVEIS_CONFIANCA:
        raise ValueError(f"confianca inválida: {confianca!r} (esperado um de {NBA_V2_NIVEIS_CONFIANCA})")

    bloqueios_politica = bloqueios_politica or []
    if bloqueios_politica:
        raise ValueError(
            f"recomendação recusada: bloqueio(s) de política ativo(s) {bloqueios_politica} — "
            "next best action não pode ser emitida enquanto uma política impede avançar"
        )

    _validar_spin_gap(spin_cobertura, spin_gap_campo)

    if meddpicc_gap_item is not None:
        if meddpicc_estado is None:
            raise ValueError("meddpicc_estado obrigatório quando meddpicc_gap_item é informado")
        _validar_meddpicc_gap(meddpicc_estado, meddpicc_gap_item)

    if confianca == "alta" and historico_insight is None:
        raise ValueError(
            "confianca='alta' exige historico_insight com evidência real — conhecimento "
            "disponível insuficiente para essa confiança"
        )
    if historico_insight is not None:
        _validar_historico_insight(historico_insight)

    return {
        "titulo": titulo,
        "por_que": por_que,
        "spin_gap": spin_gap_campo,
        "meddpicc_gap": meddpicc_gap_item,
        "historico": historico_insight["insight"] if historico_insight else None,
        "confianca": confianca,
        "pergunta": pergunta,
        "evite": evite,
    }
