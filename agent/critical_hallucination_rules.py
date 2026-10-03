"""
SALEIA — agent/critical_hallucination_rules.py

Tarefa D2 de docs/tasks-prompt-mestre-v2-restante.md — define
"alucinação crítica" e a separa das demais. A `hallucination_rate` da
Fase 19.1 conta toda afirmação sem lastro (inclusive paráfrase inócua);
o critério da Fase 25 é "critical hallucination ≈ 0", que precisa de uma
definição objetiva. Função pura, determinística, zero IA.

**Alucinação crítica** = algo na saída do motor que pode levar o vendedor
a dizer uma inverdade concreta ao cliente, e que **não aparece em nada
do que o motor recebeu** (`texto_fonte`):

1. `numero_inventado` — preço em R$, percentual, ou número com 3+
   dígitos / "N mil|milhão" (valores, volumes, metas).
2. `promessa_de_resultado` — "garanto", "retorno garantido", "sem
   risco", "com certeza vai/vão", "100% de certeza", "prometo".
3. `dado_do_cliente_inventado` — nome próprio, e-mail ou telefone.

Campos checados: os de texto que viram fala ou raciocínio
(`next_best_action`, `next_best_question`, `reason`, `current_state`,
`hypotheses`, `evidence`). `avoid` fica de fora de propósito: lista o que
NÃO fazer ("não oferecer 20% de desconto") — um número ali é proibição,
não afirmação.

Heurística conservadora e documentada: prefere falso positivo a deixar
passar inverdade concreta (o alvo é ≈ 0). Números até 2 dígitos sem R$/%
("3 perguntas") não contam.
"""

import re
import unicodedata
from typing import Optional

CATEGORIAS_CRITICAS = ("numero_inventado", "promessa_de_resultado", "dado_do_cliente_inventado")

CAMPOS_CHECADOS = (
    "next_best_action", "next_best_question", "reason", "current_state", "hypotheses", "evidence",
)

_NUMERO = re.compile(
    r"R\$\s*\d[\d.,]*(?:\s*(?:mil|milh(?:ão|ao|ões|oes)|k))?"     # R$ 1.500 / R$ 20 mil
    r"|\d[\d.,]*\s*%"                                              # 15% / 12,5 %
    r"|\d[\d.,]*\s*(?:mil|milh(?:ão|ao|ões|oes))\b"                # 20 mil
    r"|\b\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?\b"                      # 1.500 / 20.000,00
    r"|\b\d{3,}\b",                                                # 150 / 2026
    re.IGNORECASE,
)
_PROMESSA = re.compile(
    r"\bgaranti(?:mos|do|da|a)\b|\bgaranto\b|\bgarantir(?:á|a|emos)\b|\bprometo\b|\bprometemos\b"
    r"|\bsem (?:nenhum )?risco\b|\bcom certeza (?:vai|vão|vao|irá|ira)\b|\b100\s*% de certeza\b"
    r"|\bresultado garantido\b|\bretorno garantido\b",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_TELEFONE = re.compile(r"\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}")
_NOME = re.compile(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]{2,}\b")

# Palavras com inicial maiúscula que não são dado do cliente: rótulos do
# próprio sistema/metodologia, papéis e palavras que costumam abrir frase.
_NAO_SAO_NOMES = frozenset({
    "cliente", "vendedor", "spin", "meddpicc", "situation", "problem", "implication", "need", "payoff",
    "objection", "investigation", "negotiation", "risk", "mitigation", "closing", "qualification",
    "pergunte", "pergunta", "investigue", "confirme", "explore", "quantifique", "proponha", "evite",
    "entenda", "valide", "mapeie", "aprofunde", "descubra", "identifique", "use", "mostre", "apresente",
    "recomendo", "sugiro", "agora", "antes", "depois", "hoje", "ainda", "quando", "como", "qual", "quais",
    "quanto", "quantos", "porque", "por", "para", "pra", "com", "sem", "sobre", "isso", "esse", "essa",
    "este", "esta", "ele", "ela", "eles", "elas", "nao", "não", "sim", "mas", "também", "tambem", "se",
    "dor", "impacto", "objeção", "objecao", "preço", "preco", "valor", "orçamento", "orcamento",
    "decisor", "champion", "economic", "buyer", "metrics", "ceo", "cfo", "cto", "diretor", "diretora",
    "gerente", "dono", "sócio", "socio", "equipe", "time", "empresa", "proposta", "reunião", "reuniao",
    "the", "and", "for", "with", "não", "existe", "há", "ha", "falta", "nenhum", "nenhuma",
    "segunda", "terça", "terca", "quarta", "quinta", "sexta", "sábado", "sabado", "domingo",
    "janeiro", "fevereiro", "março", "marco", "abril", "maio", "junho", "julho", "agosto",
    "setembro", "outubro", "novembro", "dezembro", "brasil", "real", "reais",
})


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFD", texto or "").encode("ascii", "ignore").decode().lower()


def _digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


def _textos_do_campo(valor) -> list:
    if isinstance(valor, str):
        return [valor]
    if isinstance(valor, (list, tuple)):
        return [v for v in valor if isinstance(v, str)]
    return []


def _numero_aparece_na_fonte(trecho: str, fonte_bruta: str, fonte_digitos_por_token: set) -> bool:
    digitos = _digitos(trecho)
    if not digitos:
        return True
    if digitos in fonte_digitos_por_token:
        return True
    # "20 mil" na saída vs "20.000"/"20000" na fonte (e vice-versa)
    if re.search(r"mil\b", trecho, re.IGNORECASE) and (digitos + "000") in fonte_digitos_por_token:
        return True
    return digitos in _digitos(fonte_bruta) and len(digitos) >= 4


def detectar_alucinacoes_criticas(saida: Optional[dict], texto_fonte: str) -> list:
    """`[{"categoria", "campo", "trecho"}]` — vazio quando a saída não
    traz nenhuma alucinação crítica. Nunca levanta."""
    if not isinstance(saida, dict):
        return []
    fonte = texto_fonte or ""
    fonte_normalizada = _sem_acento(fonte)
    fonte_digitos = {_digitos(t) for t in re.findall(r"\d[\d.,]*", fonte)}
    for t in re.findall(r"(\d[\d.,]*)\s*mil\b", fonte, re.IGNORECASE):
        fonte_digitos.add(_digitos(t) + "000")

    achados, vistos = [], set()

    def _registrar(categoria, campo, trecho):
        chave = (categoria, trecho.strip().lower())
        if chave not in vistos:
            vistos.add(chave)
            achados.append({"categoria": categoria, "campo": campo, "trecho": trecho.strip()})

    for campo in CAMPOS_CHECADOS:
        for texto in _textos_do_campo(saida.get(campo)):
            for m in _NUMERO.finditer(texto):
                if not _numero_aparece_na_fonte(m.group(0), fonte, fonte_digitos):
                    _registrar("numero_inventado", campo, m.group(0))
            for m in _PROMESSA.finditer(texto):
                if _sem_acento(m.group(0)) not in fonte_normalizada:
                    _registrar("promessa_de_resultado", campo, m.group(0))
            for m in _EMAIL.finditer(texto):
                if m.group(0).lower() not in fonte.lower():
                    _registrar("dado_do_cliente_inventado", campo, m.group(0))
            for m in _TELEFONE.finditer(texto):
                if _digitos(m.group(0)) not in _digitos(fonte):
                    _registrar("dado_do_cliente_inventado", campo, m.group(0))
            for m in _NOME.finditer(texto):
                palavra = m.group(0)
                if _sem_acento(palavra) in _NAO_SAO_NOMES:
                    continue
                # 1ª palavra de frase com maiúscula é gramática, não nome.
                antes = texto[:m.start()].rstrip()
                if not antes or antes[-1] in ".!?:\"'(—-":
                    continue
                if _sem_acento(palavra) not in fonte_normalizada:
                    _registrar("dado_do_cliente_inventado", campo, palavra)
    return achados


def taxa_alucinacao_critica(cenarios_com_critica: int, cenarios_avaliados: int) -> Optional[float]:
    """Fração de cenários/recomendações com pelo menos 1 alucinação
    crítica — a unidade que importa para o vendedor (uma recomendação com
    um preço inventado já é o problema). `None` sem amostra."""
    if not cenarios_avaliados:
        return None
    return round(cenarios_com_critica / cenarios_avaliados, 4)
