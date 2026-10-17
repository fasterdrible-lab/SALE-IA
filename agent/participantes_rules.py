""""Quem é quem" da reunião (V.1.4.186 + ext 1.4.35). Regras puras.

No começo de cada reunião o vendedor diz, na extensão, para cada nome que o
Meet mostra (o próprio "Você", às vezes o começo do e-mail), o nome real e o
papel. As falas já chegam rotuladas com o nome real; aqui está o cabeçalho
que diz à IA quem vende e quem compra. Vale só para aquela reunião.
"""
from __future__ import annotations

import json

PAPEIS = {"vendedor": "VENDEDOR", "cliente": "CLIENTE", "outro": "OUTRO"}
MAX_PARTICIPANTES = 30
MAX_NOME = 80


def _texto(valor) -> str:
    return " ".join(str(valor or "").split())[:MAX_NOME]


def normalizar_participantes(lista) -> list[dict]:
    """Lista da extensão → [{nome_meet, nome, papel}] limpa. Papel fora de
    vendedor/cliente/outro vira "" (não informado). Repetidos (mesmo nome
    real) ficam só uma vez. Entrada inválida → []."""
    if not isinstance(lista, list):
        return []
    vistos: set[str] = set()
    saida: list[dict] = []
    for item in lista[:MAX_PARTICIPANTES]:
        if not isinstance(item, dict):
            continue
        nome_meet = _texto(item.get("nome_meet"))
        nome = _texto(item.get("nome")) or nome_meet
        if not nome:
            continue
        papel = str(item.get("papel") or "").strip().lower()
        if papel not in PAPEIS:
            papel = ""
        chave = nome.lower()
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append({"nome_meet": nome_meet, "nome": nome, "papel": papel})
    return saida


def tem_papel_informado(participantes: list[dict]) -> bool:
    """Só vale mandar à IA se o vendedor disse ao menos 1 cliente/outro:
    "Você = vendedor" sozinho é o padrão da extensão, não informação nova."""
    return any(p.get("papel") in ("cliente", "outro") for p in participantes or [])


def cabecalho_participantes(participantes: list[dict]) -> str:
    """Bloco posto antes da transcrição enviada à IA. Vazio quando o
    vendedor não disse papel de ninguém além dele mesmo — aí a IA deduz
    pela conversa, como antes."""
    if not tem_papel_informado(participantes):
        return ""
    linhas = []
    for p in participantes:
        papel = PAPEIS.get(p.get("papel") or "", "papel não informado")
        nome_meet = p.get("nome_meet") or ""
        extra = ""
        if nome_meet and nome_meet != p["nome"] and nome_meet != "Você":
            extra = f' (no Meet: "{nome_meet}")'
        linhas.append(f"- {p['nome']}{extra}: {papel}")
    clientes = [p["nome"] for p in participantes if p.get("papel") == "cliente"]
    instrucao = (
        "Analise as falas do(s) CLIENTE(s); as do VENDEDOR são só contexto. "
        "Toda fala ou pergunta sugerida é dita PELO vendedor PARA o cliente"
        + (f" — chame o cliente de {', '.join(clientes)}" if clientes else "")
        + ", nunca pelo nome do vendedor."
    )
    return (
        "QUEM É QUEM NESTA REUNIÃO (informado pelo vendedor; vale mais que qualquer "
        "outra pista sobre quem vende; as falas abaixo estão rotuladas com estes nomes):\n"
        + "\n".join(linhas) + "\n" + instrucao + "\n\n"
    )


def para_json(participantes: list[dict]) -> str:
    return json.dumps(participantes or [], ensure_ascii=False)


def de_json(texto) -> list[dict]:
    if not texto:
        return []
    try:
        return normalizar_participantes(json.loads(texto) if isinstance(texto, str) else texto)
    except (ValueError, TypeError):
        return []
