"""
SALEIA — api/otimizacao_shadow.py
Otimizacao — Cost Intelligence Fase 5, SHADOW MODE.

IMPORTANTE: assim como api/cost_router.py (Fase 4), este modulo nunca
altera o resultado de uma chamada de IA real — so calcula e REGISTRA o
que uma otimizacao (cache de resposta, corte de contexto, bloqueio de
loop caro por reuniao) teria feito, sempre depois do resultado real ja
decidido. `avaliar_otimizacoes_shadow()` e sempre melhor esforco.

3 tipos de decisao (campo `tipo` em OtimizacaoDecisao):
- cache_hit: a mesma chamada (feature+prompt+conteudo identicos) ja
  tinha sido feita ha pouco — um cache real teria evitado a chamada
  inteira.
- contexto_truncado: o prompt enviado passou do teto configurado —
  um corte real teria reduzido o custo de entrada.
- loop_bloqueado: o custo acumulado da reuniao passou de um limite
  configuravel (desligado por padrao — nunca um limite inventado).
"""

from __future__ import annotations

import hashlib
import os
import time
from collections import OrderedDict

from api.cost_engine import ProviderUsage, calcular_custo

_CONTEXTO_MAX_CHARS_DEFAULT = 20000

_CACHE_TTL_S = 600  # 10min
_CACHE_MAX_ENTRIES = 500
_cache_respostas: "OrderedDict[str, dict]" = OrderedDict()

_CUSTO_REUNIAO_CACHE_TTL_S = 60
_custo_reuniao_cache: dict[str, tuple[float, float]] = {}  # meeting_id -> (custo_usd, ts)


def _contexto_max_chars() -> int:
    return int(os.getenv("OTIMIZACAO_CONTEXTO_MAX_CHARS", _CONTEXTO_MAX_CHARS_DEFAULT))


def _loop_max_custo_usd() -> float | None:
    valor = os.getenv("OTIMIZACAO_LOOP_MAX_CUSTO_USD")
    if not valor:
        return None
    try:
        return float(valor)
    except ValueError:
        return None


def _prompt_hash(system_prompt: str) -> str:
    return hashlib.sha256((system_prompt or "").encode("utf-8")).hexdigest()[:12]


def _chave_cache(feature: str, system_prompt: str, user_content: str) -> str:
    bruto = f"{feature}|{system_prompt}|{user_content}".encode("utf-8", errors="ignore")
    return hashlib.sha256(bruto).hexdigest()


def _avaliar_cache_shadow(feature: str, system_prompt: str, user_content: str, custo_real_usd: float) -> dict | None:
    """Verifica se uma chamada identica ja estava no cache (shadow) antes
    de registrar a atual — nunca serve a resposta de verdade."""
    chave = _chave_cache(feature, system_prompt, user_content)
    agora = time.time()

    decisao = None
    anterior = _cache_respostas.get(chave)
    if anterior is not None and (agora - anterior["ts"]) < _CACHE_TTL_S:
        decisao = {
            "tipo": "cache_hit",
            "economia_estimada_usd": custo_real_usd,
            "detalhe": f"chave repetida ha {agora - anterior['ts']:.0f}s",
        }

    _cache_respostas[chave] = {"custo_usd": custo_real_usd, "ts": agora}
    _cache_respostas.move_to_end(chave)
    while len(_cache_respostas) > _CACHE_MAX_ENTRIES:
        _cache_respostas.popitem(last=False)

    return decisao


def _avaliar_contexto_shadow(
    provider: str, model: str, system_prompt: str, user_content: str,
    usage: ProviderUsage, usage_source: str, custo_real_usd: float,
) -> dict | None:
    tamanho_total = len(system_prompt or "") + len(user_content or "")
    limite = _contexto_max_chars()
    if tamanho_total <= limite:
        return None

    fracao_cortada = (tamanho_total - limite) / tamanho_total
    tokens_reduzidos = int(usage.input_tokens * fracao_cortada)
    usage_reduzido = ProviderUsage(
        input_tokens=max(0, usage.input_tokens - tokens_reduzidos),
        output_tokens=usage.output_tokens,
        cached_input_tokens=usage.cached_input_tokens,
        reasoning_output_tokens=usage.reasoning_output_tokens,
    )
    custo_reduzido = calcular_custo(provider, model, usage_reduzido, usage_source)
    economia = round(custo_real_usd - custo_reduzido.cost_usd, 6)

    return {
        "tipo": "contexto_truncado",
        "economia_estimada_usd": economia,
        "detalhe": f"tamanho={tamanho_total} chars, limite={limite} chars",
    }


def _custo_acumulado_reuniao(meeting_id: str) -> float:
    agora = time.time()
    cache = _custo_reuniao_cache.get(meeting_id)
    if cache is not None and (agora - cache[1]) < _CUSTO_REUNIAO_CACHE_TTL_S:
        return cache[0]

    from api.database import custo_por_reuniao
    custo = custo_por_reuniao(meeting_id).get("total_usd", 0.0)
    _custo_reuniao_cache[meeting_id] = (custo, agora)
    return custo


def _avaliar_loop_caro_shadow(meeting_id: str | None, feature: str) -> dict | None:
    limite = _loop_max_custo_usd()
    if not limite or not meeting_id:
        return None

    acumulado = _custo_acumulado_reuniao(meeting_id)
    if acumulado < limite:
        return None

    return {
        "tipo": "loop_bloqueado",
        "economia_estimada_usd": 0.0,  # o bloqueio impediria a PROXIMA chamada, nao esta
        "detalhe": f"custo acumulado da reuniao={acumulado:.4f} USD, limite={limite:.4f} USD",
    }


def avaliar_otimizacoes_shadow(
    *,
    feature: str,
    provider: str,
    model: str,
    system_prompt: str,
    user_content: str,
    usage: ProviderUsage,
    usage_source: str,
    custo_real_usd: float,
    meeting_id: str | None = None,
) -> None:
    """Registra, em modo shadow, quais otimizacoes se aplicariam a essa
    chamada de IA real ja concluida — melhor esforco absoluto, nunca
    lanca. Chamado de dentro de api/ai_router.py::chamar_ia DEPOIS do
    resultado real ja ter sido decidido."""
    try:
        prompt_hash = _prompt_hash(system_prompt)
        decisoes = [
            _avaliar_cache_shadow(feature, system_prompt, user_content, custo_real_usd),
            _avaliar_contexto_shadow(provider, model, system_prompt, user_content, usage, usage_source, custo_real_usd),
            _avaliar_loop_caro_shadow(meeting_id, feature),
        ]

        from api.database import registrar_decisao_otimizacao
        for decisao in decisoes:
            if decisao is None:
                continue
            registrar_decisao_otimizacao(
                tipo=decisao["tipo"],
                feature=feature,
                meeting_id=meeting_id,
                prompt_hash=prompt_hash,
                custo_real_usd=custo_real_usd,
                economia_estimada_usd=decisao["economia_estimada_usd"],
                detalhe=decisao["detalhe"],
            )
    except Exception:
        pass  # melhor esforco absoluto — nunca deve afetar a chamada de IA real
