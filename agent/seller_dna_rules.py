# -*- coding: utf-8 -*-
"""
SALEIA — agent/seller_dna_rules.py

Seller DNA (FASE 15 / TAREFAS 15.1 e 15.2 do "PROMPT MESTRE — SALE-IA
V2"). Função pura, nenhuma chamada de IA, nenhum acesso a banco — mesmo
padrão de agent/seller_scorecard_rules.py/agent/deal_risk_rules.py.

TAREFA 15.1 — perfil comportamental do vendedor nos 12 campos literais
do prompt mestre (`SELLER_DNA_CAMPOS`). Regra explícita — "não clonar
personalidade a partir de poucas conversas, exigir amostra mínima
configurável" — imposta estruturalmente: `construir_seller_dna()`
recusa (`ValueError`) montar qualquer perfil quando
`n_reunioes_analisadas` for menor que o mínimo exigido.

TAREFA 15.2 — regra central do prompt mestre: "'André costuma fazer X'
não significa 'X funciona'. SellerDNA registra comportamento, Sales
Science mede eficácia, nunca misturar os dois." Garantida
estruturalmente, não só por instrução: todo valor de campo do
SellerDNA passa por `validar_sem_alegacao_de_eficacia()`, que recusa
qualquer texto contendo linguagem de eficácia/resultado — quem quiser
saber SE um comportamento funciona precisa ir ao Sales Science Engine
(Fase 13, `agent/sales_science_engine.py`), nunca ao SellerDNA.
"""

from typing import Optional

# TAREFA 15.1 — os 12 campos literais do prompt mestre. Vocabulário
# fechado: chave fora daqui levanta ValueError.
SELLER_DNA_CAMPOS = (
    "communication_style",
    "opening_patterns",
    "discovery_style",
    "question_patterns",
    "storytelling_patterns",
    "negotiation_patterns",
    "objection_patterns",
    "pricing_style",
    "closing_patterns",
    "language_patterns",
    "preferred_phrases",
    "forbidden_phrases",
)

# Decisão desta rodada — o prompt mestre pede "amostra mínima
# configurável" mas não define o número exato (diferente do n>=30 de
# `win_loss_rules.AMOSTRA_MINIMA_PADRAO`, que é sobre significância
# estatística). Aqui o objetivo é outro: evitar generalizar um estilo
# a partir de 1-2 reuniões atípicas. 10 reuniões distintas já dão
# repetição suficiente de padrão sem exigir volume estatístico.
# Sempre sobrescrevível por chamada.
SELLER_DNA_AMOSTRA_MINIMA_PADRAO = 10

# TAREFA 15.2 — termos que indicam alegação de eficácia/resultado, não
# descrição de comportamento. Nenhum campo do SellerDNA pode conter
# esses termos — essa é a garantia estrutural da regra "nunca misturar
# os dois conceitos".
TERMOS_ALEGACAO_EFICACIA = (
    "funciona", "funcionam", "eficaz", "eficácia",
    "melhora a conversão", "aumenta a conversão",
    "melhora o fechamento", "aumenta o fechamento",
    "comprovado", "comprova que", "prova que",
    "resulta em mais vendas", "gera mais resultado",
    "é a melhor forma de vender", "vende mais",
)


def amostra_suficiente_seller_dna(n_reunioes_analisadas: int, minimo: int = SELLER_DNA_AMOSTRA_MINIMA_PADRAO) -> bool:
    return n_reunioes_analisadas >= minimo


def validar_sem_alegacao_de_eficacia(campo: str, valor) -> None:
    """TAREFA 15.2 — recusa (ValueError) qualquer valor de campo que
    contenha linguagem de eficácia/resultado. `valor` pode ser string,
    lista/tupla de strings, ou None (campo ainda sem observação)."""
    if valor is None:
        return
    textos = valor if isinstance(valor, (list, tuple)) else [valor]
    for texto in textos:
        texto_normalizado = str(texto).lower()
        for termo in TERMOS_ALEGACAO_EFICACIA:
            if termo in texto_normalizado:
                raise ValueError(
                    f"campo {campo!r} contém alegação de eficácia ({termo!r}): {texto!r} — "
                    "SellerDNA registra comportamento, nunca eficácia (isso é papel do "
                    "Sales Science Engine, Fase 13)"
                )


def construir_seller_dna(
    seller_id: str,
    n_reunioes_analisadas: int,
    observacoes_por_campo: Optional[dict] = None,
    minimo_amostra: int = SELLER_DNA_AMOSTRA_MINIMA_PADRAO,
) -> dict:
    """TAREFA 15.1 — monta o perfil SellerDNA dos 12 campos literais a
    partir de observações já extraídas pelo chamador (uma reunião real
    ou um conjunto delas — este módulo nunca lê transcrição).

    Recusa (`ValueError`) quando `n_reunioes_analisadas` for menor que
    `minimo_amostra` — nunca clona personalidade a partir de poucas
    conversas. Recusa também (via `validar_sem_alegacao_de_eficacia`)
    qualquer campo cujo texto meça eficácia em vez de comportamento.

    `observacoes_por_campo`: dict opcional `{campo: valor}` — chave
    fora de `SELLER_DNA_CAMPOS` levanta `ValueError`. Campo ausente do
    dict é tratado como "sem observação ainda" (`None`), nunca como
    erro."""
    if seller_id is None or not str(seller_id).strip():
        raise ValueError("seller_id obrigatório e não pode ser vazio")
    if n_reunioes_analisadas is None or n_reunioes_analisadas < 0:
        raise ValueError("n_reunioes_analisadas precisa ser um inteiro >= 0")
    if not amostra_suficiente_seller_dna(n_reunioes_analisadas, minimo_amostra):
        raise ValueError(
            f"amostra insuficiente para construir SellerDNA de {seller_id!r}: "
            f"{n_reunioes_analisadas} reunião(ões) analisada(s), mínimo exigido é "
            f"{minimo_amostra} — evita clonar personalidade a partir de poucas conversas"
        )

    observacoes_por_campo = observacoes_por_campo or {}
    campos_invalidos = set(observacoes_por_campo) - set(SELLER_DNA_CAMPOS)
    if campos_invalidos:
        raise ValueError(f"campo(s) fora do vocabulário SellerDNA: {sorted(campos_invalidos)}")

    perfil = {}
    for campo in SELLER_DNA_CAMPOS:
        valor = observacoes_por_campo.get(campo)
        validar_sem_alegacao_de_eficacia(campo, valor)
        perfil[campo] = valor

    return {
        "seller_id": seller_id,
        "n_reunioes_analisadas": n_reunioes_analisadas,
        "campos": perfil,
    }


def campos_sem_observacao(seller_dna: dict) -> list:
    """Lista os campos cujo valor veio `None` (sem observação ainda) —
    útil pro Dashboard sinalizar "dado insuficiente" em vez de
    esconder o campo, mesmo princípio de
    `seller_scorecard_rules.dimensoes_sem_evidencia()`."""
    return [campo for campo, valor in seller_dna["campos"].items() if valor is None]
