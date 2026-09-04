"""
SALEIA — api/otimizacao.py
Otimizacao de custo de IA — Cost Intelligence Fase 5.

ATIVO EM PRODUCAO desde V.1.4.60 (confirmado explicitamente com o
usuario em 04/09/2026, apos rodar em shadow mode desde V.1.4.58) —
diferente do resto do Cost Intelligence, este modulo MUDA o resultado
real de chamadas de IA:
  - cache_ativo(): serve uma resposta anterior identica sem chamar IA
  - contexto_ativo(): corta user_content antes de mandar pro provedor
  - loop_ativo(): bloqueia (HTTP 429) chamadas novas de uma reuniao que
    ja passou do limite de custo configurado

Cada mecanismo tem seu proprio kill-switch por env
(OTIMIZACAO_{CACHE,CONTEXTO,LOOP}_ATIVO, default "true") — desligar
qualquer um e so trocar pra "false" no .env da VPS + systemctl restart
saleia, sem precisar reverter codigo.

Chamado de dentro de api/ai_router.py::chamar_ia — ver esse arquivo pra
entender exatamente onde cada funcao entra no fluxo real.
"""

from __future__ import annotations

import hashlib
import os
import time
from collections import OrderedDict

from fastapi import HTTPException

_CONTEXTO_MAX_CHARS_DEFAULT = 20000

_CACHE_TTL_S = 600  # 10min
_CACHE_MAX_ENTRIES = 500
_cache_respostas: "OrderedDict[str, dict]" = OrderedDict()

_CUSTO_REUNIAO_CACHE_TTL_S = 60
_custo_reuniao_cache: dict[str, tuple[float, float]] = {}  # meeting_id -> (custo_usd, ts)


def _flag_ativo(nome_env: str) -> bool:
    return os.getenv(nome_env, "true").strip().lower() not in ("false", "0", "")


def cache_ativo() -> bool:
    return _flag_ativo("OTIMIZACAO_CACHE_ATIVO")


def contexto_ativo() -> bool:
    return _flag_ativo("OTIMIZACAO_CONTEXTO_ATIVO")


def loop_ativo() -> bool:
    return _flag_ativo("OTIMIZACAO_LOOP_ATIVO")


def _contexto_max_chars() -> int:
    return int(os.getenv("OTIMIZACAO_CONTEXTO_MAX_CHARS", _CONTEXTO_MAX_CHARS_DEFAULT))


def loop_max_custo_usd() -> float | None:
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


# ─────────────────────────────────────────────
# Cache de resposta
# ─────────────────────────────────────────────

def buscar_no_cache(feature: str, system_prompt: str, user_content: str) -> dict | None:
    """Devolve uma copia do resultado cacheado se cache_ativo() e houver
    hit dentro do TTL — None caso contrario. Nao remove a entrada
    (chamadas identicas subsequentes dentro do TTL tambem acertam)."""
    if not cache_ativo():
        return None
    entrada = _cache_respostas.get(_chave_cache(feature, system_prompt, user_content))
    if entrada is None or (time.time() - entrada["ts"]) >= _CACHE_TTL_S:
        return None
    return dict(entrada["resultado"])


def guardar_no_cache(feature: str, system_prompt: str, user_content: str, resultado: dict) -> None:
    if not cache_ativo():
        return
    chave = _chave_cache(feature, system_prompt, user_content)
    _cache_respostas[chave] = {"resultado": dict(resultado), "ts": time.time()}
    _cache_respostas.move_to_end(chave)
    while len(_cache_respostas) > _CACHE_MAX_ENTRIES:
        _cache_respostas.popitem(last=False)


def registrar_cache_hit(*, feature: str, meeting_id: str | None, system_prompt: str, custo_evitado_usd: float) -> None:
    """Melhor esforco — nunca lanca."""
    try:
        from api.database import registrar_decisao_otimizacao
        registrar_decisao_otimizacao(
            tipo="cache_hit", feature=feature, meeting_id=meeting_id,
            prompt_hash=_prompt_hash(system_prompt), custo_real_usd=0.0,
            economia_estimada_usd=custo_evitado_usd,
            detalhe="resposta servida do cache — chamada de IA real evitada",
        )
    except Exception:
        pass


# ─────────────────────────────────────────────
# Corte de contexto
# ─────────────────────────────────────────────

def aplicar_corte_contexto(system_prompt: str, user_content: str) -> tuple[str, str, bool]:
    """So corta user_content (a parte dinamica/dados) — nunca
    system_prompt (instrucoes; cortar isso arrisca quebrar formato de
    saida/regras). Tail-slice: mantem o FIM do conteudo, mesmo padrao ja
    usado em api/processador_tempo_real.py::_limitar_contexto_ia."""
    system_prompt = system_prompt or ""
    user_content = user_content or ""
    if not contexto_ativo():
        return system_prompt, user_content, False

    limite = _contexto_max_chars()
    tamanho_total = len(system_prompt) + len(user_content)
    if tamanho_total <= limite:
        return system_prompt, user_content, False

    max_user = max(0, limite - len(system_prompt))
    return system_prompt, user_content[-max_user:], True


def registrar_corte_contexto(
    *, feature: str, meeting_id: str | None, provider: str, model: str,
    system_prompt: str, custo_usd: float, chars_cortados: int,
) -> None:
    """Melhor esforco — nunca lanca. Estima a economia a partir dos
    caracteres cortados (heuristica char/4, mesma de api/cost_engine.py)
    e do preco de input do modelo — nao ha uma chamada "sem corte" real
    pra comparar, diferente do calculo que era feito em shadow mode."""
    try:
        from api.database import registrar_decisao_otimizacao
        from api.pricing_catalog import obter_preco
        tokens_economizados = max(0, int(chars_cortados / 4))
        preco = obter_preco(provider, model)
        economia = round(tokens_economizados * preco.input_per_million / 1_000_000, 6)
        registrar_decisao_otimizacao(
            tipo="contexto_truncado", feature=feature, meeting_id=meeting_id,
            prompt_hash=_prompt_hash(system_prompt), custo_real_usd=custo_usd,
            economia_estimada_usd=economia,
            detalhe=f"cortados {chars_cortados} chars, limite={_contexto_max_chars()} chars",
        )
    except Exception:
        pass


# ─────────────────────────────────────────────
# Bloqueio de loop caro por reuniao
# ─────────────────────────────────────────────

def _custo_acumulado_reuniao(meeting_id: str) -> float:
    agora = time.time()
    cache = _custo_reuniao_cache.get(meeting_id)
    if cache is not None and (agora - cache[1]) < _CUSTO_REUNIAO_CACHE_TTL_S:
        return cache[0]

    from api.database import custo_por_reuniao
    custo = custo_por_reuniao(meeting_id).get("total_usd", 0.0)
    _custo_reuniao_cache[meeting_id] = (custo, agora)
    return custo


def verificar_loop_caro(meeting_id: str | None, feature: str, system_prompt: str) -> None:
    """Levanta HTTPException(429) se loop_ativo(), um limite estiver
    configurado (OTIMIZACAO_LOOP_MAX_CUSTO_USD — sem default, desligado
    ate o admin configurar) e o custo acumulado da reuniao ja tiver
    passado dele.

    429, nunca 503: agent/multiagente/claude_fallback.py so aciona o
    fallback pra Conta Claude pessoal em HTTPException(503)
    especificamente (`if exc.status_code != 503: raise`) — um loop caro
    bloqueado no orcamento central nao pode virar gasto na assinatura
    pessoal do vendedor, isso derrotaria o proposito do bloqueio.
    """
    if not loop_ativo() or not meeting_id:
        return
    limite = loop_max_custo_usd()
    if not limite:
        return

    acumulado = _custo_acumulado_reuniao(meeting_id)
    if acumulado < limite:
        return

    try:
        from api.database import registrar_decisao_otimizacao
        registrar_decisao_otimizacao(
            tipo="loop_bloqueado", feature=feature, meeting_id=meeting_id,
            prompt_hash=_prompt_hash(system_prompt), custo_real_usd=0.0,
            economia_estimada_usd=0.0,
            detalhe=f"custo acumulado={acumulado:.4f} USD, limite={limite:.4f} USD",
        )
    except Exception:
        pass

    raise HTTPException(
        status_code=429,
        detail={
            "erro": "Limite de custo de IA desta reuniao foi atingido.",
            "custo_acumulado_usd": round(acumulado, 6),
            "limite_usd": limite,
        },
    )
