"""Turnos temporizados por falante — A8 (V.1.4.187 + ext 1.4.37). Regras puras.

A extensão manda cada fala com o tempo em que apareceu e parou de crescer
na legenda do Meet (ms desde 1970). Aqui: limpeza do que chega, papel de
cada falante (pelo "quem é quem" da sessão, `agent/participantes_rules.py`)
e as métricas da conversa por reunião e por vendedor, usando a fórmula já
existente `agent/conversation_metrics_rules.calcular_metricas_conversa`
(Fase 11.1, que até aqui nunca teve dado).

Limitação: o tempo é o da legenda, não o do áudio (~1 s de atraso, pausas
curtas somem). Serve para % de fala e monólogos; interrupção é aproximada.
"""
from __future__ import annotations

import re

from agent.conversation_metrics_rules import PALAVRAS_ABERTURA_PADRAO, _tipo_pergunta, calcular_metricas_conversa

MAX_TURNOS_POR_ENVIO = 300
MAX_DURACAO_MS = 10 * 60 * 1000
MIN_EPOCH_MS = 1_600_000_000_000  # 2020: descarta relógio/valor absurdo
MAX_TEXTO = 2000
MAX_FALANTE = 120
NAO_IDENTIFICADO = "não identificado"


def _int(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def normalizar_turnos(lista) -> list[dict]:
    """Lista da extensão → [{falante, inicio_ms, fim_ms, texto}] válida.
    Fora: sem falante, tempo inválido, fim < início, fala > 10 min."""
    if not isinstance(lista, list):
        return []
    saida = []
    for item in lista[:MAX_TURNOS_POR_ENVIO]:
        if not isinstance(item, dict):
            continue
        falante = " ".join(str(item.get("falante") or "").split())[:MAX_FALANTE]
        inicio, fim = _int(item.get("inicio_ms")), _int(item.get("fim_ms"))
        if not falante or inicio is None or fim is None:
            continue
        if inicio < MIN_EPOCH_MS or fim < inicio or fim - inicio > MAX_DURACAO_MS:
            continue
        saida.append({"falante": falante, "inicio_ms": inicio, "fim_ms": fim,
                      "texto": str(item.get("texto") or "")[:MAX_TEXTO]})
    return saida


def _norm(texto) -> str:
    import unicodedata
    t = unicodedata.normalize("NFD", str(texto or ""))
    return "".join(c for c in t if unicodedata.category(c) != "Mn").strip().lower()


def papel_do_falante(participantes: list[dict], falante: str) -> tuple[str, bool]:
    """(papel, inferido). Papel informado no "quem é quem" vale; sem nenhum
    cliente marcado, quem não é vendedor conta como cliente (inferido);
    "outro" e "Não identificado" ficam de fora (papel "")."""
    n = _norm(falante)
    if not n or n == _norm(NAO_IDENTIFICADO):
        return "", False
    if n == "cliente":  # áudio da aba (Whisper) é sempre o outro lado
        return "cliente", False
    tem_cliente = any(p.get("papel") == "cliente" for p in participantes or [])
    achado = next((p for p in participantes or [] if _norm(p.get("nome")) == n), None)
    if achado and achado.get("papel") in ("vendedor", "cliente"):
        return achado["papel"], False
    if achado and achado.get("papel") == "outro":
        return "", False
    if n == "vendedor":
        return "vendedor", False
    return ("", False) if tem_cliente else ("cliente", True)


def turnos_para_metricas(turnos: list[dict], participantes: list[dict]) -> tuple[list[dict], bool]:
    """Formato de `calcular_metricas_conversa`: speaker vendedor/cliente/
    incerto, start/end em segundos desde a 1ª fala."""
    if not turnos:
        return [], False
    zero = min(t["inicio_ms"] for t in turnos)
    inferido = False
    saida = []
    for t in turnos:
        papel, inf = papel_do_falante(participantes, t["falante"])
        inferido = inferido or inf
        saida.append({"speaker": papel or "incerto",
                      "start": (t["inicio_ms"] - zero) / 1000.0,
                      "end": (t["fim_ms"] - zero) / 1000.0,
                      "text": t.get("texto") or ""})
    return saida, inferido


_PERGUNTA_RE = re.compile(r"[^.!?…]*\?")


def perguntas_do_texto(texto: str) -> list[str]:
    """Cada frase terminada em "?" da fala. Na legenda a pergunta costuma
    vir no fim de uma fala com várias frases ("Bom dia, Ana. Como vocês
    fazem hoje?") — a regra da Fase 11.1 olhava só o começo da fala
    inteira e chamava isso de pergunta fechada."""
    return [p.strip() for p in _PERGUNTA_RE.findall(texto or "") if len(p.strip()) > 1]


def metricas_da_reuniao(turnos: list[dict], participantes: list[dict]) -> dict:
    """Métricas de uma reunião. `disponivel` False sem fala com tempo de
    vendedor ou cliente. Perguntas: uma por frase com "?" das falas do
    vendedor, aberta/fechada pela mesma regra da Fase 11.1."""
    turns, inferido = turnos_para_metricas(turnos, participantes)
    base = calcular_metricas_conversa(turns)
    perguntas = [p for t in turns if t["speaker"] == "vendedor" for p in perguntas_do_texto(t["text"])]
    abertas = sum(1 for p in perguntas if _tipo_pergunta(p, PALAVRAS_ABERTURA_PADRAO) == "aberta")
    base["questions_total"], base["open_questions"] = len(perguntas), abertas
    base["closed_questions"] = len(perguntas) - abertas
    tempo_v = sum(max(0.0, t["end"] - t["start"]) for t in turns if t["speaker"] == "vendedor")
    tempo_c = sum(max(0.0, t["end"] - t["start"]) for t in turns if t["speaker"] == "cliente")
    if tempo_v + tempo_c <= 0:
        return {"disponivel": False, "motivo": "Sem falas com tempo de vendedor ou cliente nesta reunião "
                "(extensão anterior à 1.4.37 ou só falas \"Não identificado\").", "turnos": len(turnos)}
    return {
        "disponivel": True,
        "turnos": len(turnos),
        "tempo_vendedor_s": round(tempo_v, 1),
        "tempo_cliente_s": round(tempo_c, 1),
        "seller_talk_ratio": base["seller_talk_ratio"],
        "customer_talk_ratio": base["customer_talk_ratio"],
        "questions_total": base["questions_total"],
        "open_questions": base["open_questions"],
        "closed_questions": base["closed_questions"],
        "interruptions": base["interruptions"],
        "monologues": base["monologues"],
        "papeis_inferidos": inferido,
    }


def agregar_vendedor(metricas: list[dict]) -> dict:
    """Seller Coaching: Talk Ratio = tempo total do vendedor / tempo total
    (ponderado pelo tempo, não média de %); Question Quality = perguntas
    abertas / perguntas. Só reuniões com `disponivel`."""
    validas = [m for m in metricas or [] if m.get("disponivel")]
    if not validas:
        return {}
    tv = sum(m["tempo_vendedor_s"] for m in validas)
    tc = sum(m["tempo_cliente_s"] for m in validas)
    perguntas = sum(m["questions_total"] for m in validas)
    abertas = sum(m["open_questions"] for m in validas)
    return {
        "reunioes": len(validas),
        "seller_talk_ratio": tv / (tv + tc) if tv + tc > 0 else None,
        "tempo_vendedor_s": round(tv, 1),
        "tempo_cliente_s": round(tc, 1),
        "questions_total": perguntas,
        "open_questions": abertas,
        "closed_questions": perguntas - abertas,
        "open_question_rate": abertas / perguntas if perguntas else None,
        "monologues": sum(m["monologues"] for m in validas),
        "papeis_inferidos": any(m.get("papeis_inferidos") for m in validas),
    }
