"""
scripts/loadtest/fake_ai.py — D7 (teste de carga): servidor que imita a API
de chat do DeepSeek (compatível com a OpenAI) para a instância de teste.

- Atraso por pedido sorteado da distribuição REAL do DeepSeek em produção
  (21.241 chamadas de 12-25/10/2026): p50 2,1 s, p90 5,6 s, p99 8,9 s.
- Resposta: um JSON "superconjunto" com as chaves que coach, extratores e
  motor leem — válido para todos, sem conteúdo real.
- Conta pedidos em andamento (a "fila" da IA), total e tokens de entrada
  (len(prompt)/4, os prompts são os de produção) em GET /stats.

Nunca fala com provedor real. Uso (na VPS):
    venv/bin/python -m uvicorn scripts.loadtest.fake_ai:app --host 127.0.0.1 --port 8099
"""
from __future__ import annotations

import asyncio
import bisect
import json
import random
import time

from fastapi import FastAPI, Request

# (quantil, ms) medidos em produção — interpolação linear entre os pontos.
QUANTIS_MS = [(0.0, 400), (0.05, 779), (0.1, 913), (0.25, 1250), (0.5, 2109),
              (0.75, 3321), (0.9, 5649), (0.95, 6863), (0.99, 8928), (1.0, 12000)]
SAIDA_TOKENS_MEDIA = 450  # média ponderada das features de produção

RESPOSTA = {
    # coach / agentes do tempo real
    "dicas": ["Pergunte sobre o impacto financeiro do problema."],
    "alertas": [], "acoes_recomendadas": [],
    "proxima_pergunta": "O que acontece se isso continuar pelos próximos 6 meses?",
    "next_best_question": {"categoria": "implicacao", "pergunta": "E o impacto disso?", "objetivo": "aprofundar",
                           "motivo": "teste de carga", "impacto": "medio"},
    "score_compra": 50, "score": 50, "resumo": "teste de carga",
    "perfil_disc": {"tipo": "D", "confianca": 0.5}, "mapa_financeiro": {},
    # extratores
    "objections": [], "category": "PRICE", "categoria": "PRICE", "facts": [], "fatos": [], "signals": [],
    "known": [], "events": [], "items": [], "evidence": [], "motivation": None, "confidence": 0.5,
    "hypothesis": None, "evidence_quote": None,
    # motor (SalesReasoningEngine)
    "current_state": "discovery", "recommended_framework": "SPIN", "next_best_action": "Aprofundar a dor.",
    "reason": "teste de carga", "hypotheses": [], "missing_information": [], "avoid": [],
}

app = FastAPI()
estado = {"em_andamento": 0, "max_em_andamento": 0, "total": 0, "tokens_entrada": 0, "tokens_saida": 0,
          "inicio": time.time()}


def sortear_atraso_s() -> float:
    u = random.random()
    qs = [q for q, _ in QUANTIS_MS]
    i = max(1, bisect.bisect_left(qs, u))
    (q0, v0), (q1, v1) = QUANTIS_MS[i - 1], QUANTIS_MS[i]
    return (v0 + (v1 - v0) * (u - q0) / (q1 - q0)) / 1000


@app.post("/chat/completions")
@app.post("/v1/chat/completions")
async def chat(request: Request):
    corpo = await request.json()
    prompt = "".join(str(m.get("content") or "") for m in corpo.get("messages") or [])
    entrada = max(1, len(prompt) // 4)
    saida = max(5, int(random.expovariate(1 / SAIDA_TOKENS_MEDIA)))
    estado["em_andamento"] += 1
    estado["max_em_andamento"] = max(estado["max_em_andamento"], estado["em_andamento"])
    try:
        await asyncio.sleep(sortear_atraso_s())
    finally:
        estado["em_andamento"] -= 1
    estado["total"] += 1
    estado["tokens_entrada"] += entrada
    estado["tokens_saida"] += saida
    return {
        "id": f"lt-{estado['total']}", "object": "chat.completion", "created": int(time.time()),
        "model": corpo.get("model", "deepseek-chat"),
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": json.dumps(RESPOSTA, ensure_ascii=False)}}],
        "usage": {"prompt_tokens": entrada, "completion_tokens": saida, "total_tokens": entrada + saida},
    }


@app.get("/stats")
async def stats():
    return dict(estado)


@app.post("/stats/zerar_pico")
async def zerar_pico():
    estado["max_em_andamento"] = estado["em_andamento"]
    return dict(estado)
