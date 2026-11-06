"""Prepara o que vai para a IA em cada ciclo. Função pura, sem IA nem banco.

Achado em 05/11/2026: `current_diagnosis` e `events_json` entravam sem limite
nos prompts (até 476 mil caracteres) e o corte da Fase 5
(`api/otimizacao.py::aplicar_corte_contexto`), que mantém o FIM do texto,
removia a conversa atual e as regras, que ficavam no começo. Daí:

- `limitar_*`: nada entra sem teto, e a cópia que o diagnóstico guarda dos
  eventos, momentos-chave e scores sai;
- `dividir_prompt`: regras vão para o system_prompt, que nunca é cortado. Nos
  templates, os dados ficam depois de `MARCADOR_DADOS`, com a conversa atual
  por último: se ainda sobrar excesso, sai o que importa menos.
"""
from __future__ import annotations

import json

MARCADOR_DADOS = "=== DADOS DA REUNIAO ==="

MAX_CHARS_DIAGNOSTICO = 2500
MAX_CHARS_EVENTOS = 2500
MAX_CHARS_SCORES = 800

# Já entram no prompt por campo próprio, ou são listas que só crescem.
CHAVES_FORA_DO_DIAGNOSTICO = frozenset({"key_moments", "score_history", "eventos", "events"})


def _json(valor) -> str:
    return json.dumps(valor, ensure_ascii=False)


def limitar_lista(itens, max_chars: int) -> list:
    """Os itens mais recentes (fim da lista) que cabem em `max_chars`."""
    if not isinstance(itens, list):
        return []
    mantidos: list = []
    tamanho = 2
    for item in reversed(itens):
        tamanho += len(_json(item)) + 2
        if tamanho > max_chars:
            break
        mantidos.append(item)
    return mantidos[::-1]


def limitar_diagnostico(diagnostico, max_chars: int = MAX_CHARS_DIAGNOSTICO) -> dict:
    """Diagnóstico sem as cópias. Campo que não couber sai inteiro, para o JSON
    nunca chegar quebrado à IA; os menores entram primeiro."""
    if not isinstance(diagnostico, dict):
        return {}
    mantido: dict = {}
    tamanho = 2
    campos = [(k, v) for k, v in diagnostico.items() if k not in CHAVES_FORA_DO_DIAGNOSTICO]
    for chave, valor in sorted(campos, key=lambda c: len(_json(c[1]))):
        tamanho += len(_json(chave)) + len(_json(valor)) + 4
        if tamanho > max_chars:
            break
        mantido[chave] = valor
    return mantido


def dividir_prompt(prompt: str) -> tuple:
    """`(regras, dados)`. Divide na 1ª ocorrência: as regras vêm antes de
    qualquer texto da conversa, então uma fala não muda a divisão."""
    regras, marcador, dados = (prompt or "").partition(MARCADOR_DADOS)
    if not marcador:
        return "", prompt or ""
    return regras.strip(), dados.strip()
