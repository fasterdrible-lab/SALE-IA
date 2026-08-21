"""
Central AI provider router for SALEIA.

The frontend never selects providers or receives secrets. This module owns:
- provider order
- API keys and model names
- timeouts
- fallback decisions
- in-memory circuit breaker state
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()

logger = logging.getLogger("saleia.ai")

DEFAULT_PROVIDER_ORDER = ("deepseek", "openai", "anthropic", "gemini")
PROVIDER_ALIASES = {
    "google": "gemini",
    "claude": "anthropic",
    "cloude": "anthropic",
}
FAILURES_TO_OPEN = int(os.getenv("AI_PROVIDER_FAILURES_TO_OPEN", "3"))
COOLDOWN_SECONDS = int(os.getenv("AI_PROVIDER_COOLDOWN_SECONDS", "60"))
DEFAULT_TIMEOUT_SECONDS = float(os.getenv("AI_PROVIDER_TIMEOUT_SECONDS", "30"))
ERROR_MAX_LENGTH = 220
FORBIDDEN_TRIGGER_PHRASES = (
    "deixa eu ver se entendi",
    "pelo que voce me falou",
    "pelo que você me falou",
    "foi isso que eu colhi",
    "so para confirmar",
    "só para confirmar",
)
FORBIDDEN_TRIGGER_PATTERNS = (
    r"deixa\s+eu\s+ver\s+se\s+entendi",
    r"pelo\s+que\s+voc[eé?]\s+me\s+falou",
    r"foi\s+isso\s+que\s+eu\s+colhi",
    r"s[oó?]\s+para\s+confirmar",
)
FORBIDDEN_TRIGGER_RULE = (
    "\n\nREGRA DE LINGUAGEM OBRIGATORIA:\n"
    "- Nunca use nas respostas finais as frases: "
    "\"deixa eu ver se entendi\", \"pelo que voce me falou\", "
    "\"foi isso que eu colhi\" ou \"so para confirmar\".\n"
    "- Se precisar validar entendimento, use uma formulacao natural diferente."
)
ROOT_DIR = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT_DIR / "data" / "ai_provider_order.json"
ESTIMATED_COST_INPUT_PER_MILLION = {
    "deepseek": float(os.getenv("DEEPSEEK_INPUT_COST_PER_MILLION", "0.14")),
    "openai": float(os.getenv("OPENAI_INPUT_COST_PER_MILLION", "5.0")),
    "anthropic": float(os.getenv("ANTHROPIC_INPUT_COST_PER_MILLION", "3.0")),
    "gemini": float(os.getenv("GEMINI_INPUT_COST_PER_MILLION", "0.35")),
}
ESTIMATED_COST_OUTPUT_PER_MILLION = {
    "deepseek": float(os.getenv("DEEPSEEK_OUTPUT_COST_PER_MILLION", "0.28")),
    "openai": float(os.getenv("OPENAI_OUTPUT_COST_PER_MILLION", "15.0")),
    "anthropic": float(os.getenv("ANTHROPIC_OUTPUT_COST_PER_MILLION", "15.0")),
    "gemini": float(os.getenv("GEMINI_OUTPUT_COST_PER_MILLION", "1.05")),
}


@dataclass(frozen=True)
class Provider:
    name: str
    env_keys: tuple[str, ...]
    model_env: str
    default_model: str
    caller: Callable[[str, str, str, str, float], dict]


@dataclass
class CircuitBreaker:
    name: str
    failures: int = 0
    opened_at: float = 0.0

    @property
    def available(self) -> bool:
        if self.failures < FAILURES_TO_OPEN:
            return True
        if time.time() - self.opened_at >= COOLDOWN_SECONDS:
            return True
        return False

    def register_success(self) -> None:
        self.failures = 0
        self.opened_at = 0.0

    def register_failure(self) -> None:
        self.failures += 1
        self.opened_at = time.time()
        if self.failures >= FAILURES_TO_OPEN:
            logger.warning(
                "AI circuit breaker opened for %s for %ss",
                self.name,
                COOLDOWN_SECONDS,
            )
            try:
                with _counters_lock:
                    _counters["circuit_breaker_aberturas"] += 1
            except Exception:
                pass
            try:
                from agent.alertas import alertar
                alertar(
                    f"🤖 Circuit breaker aberto: *{self.name}*\n"
                    f"Cooldown: {COOLDOWN_SECONDS}s — fallback para próximo provedor.",
                    nivel="🟠",
                )
            except Exception:
                pass


def _extract_json(text: str) -> dict:
    payload = (text or "").strip()
    if payload.startswith("```"):
        payload = payload.strip("`").strip()
        if payload.lower().startswith("json"):
            payload = payload[4:].strip()
    return json.loads(payload)


def _clean_forbidden_trigger_phrases(text: str) -> str:
    cleaned = text or ""
    for pattern in FORBIDDEN_TRIGGER_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    return cleaned.strip()


def _sanitize_ai_payload(value):
    if isinstance(value, str):
        return _clean_forbidden_trigger_phrases(value)
    if isinstance(value, list):
        return [_sanitize_ai_payload(item) for item in value]
    if isinstance(value, dict):
        return {key: _sanitize_ai_payload(item) for key, item in value.items()}
    return value


def _normalize_provider_name(raw_name: str) -> str | None:
    name = PROVIDER_ALIASES.get(raw_name.strip().lower(), raw_name.strip().lower())
    return name if name in PROVIDERS else None


def _default_provider_names() -> list[str]:
    return [name for name in DEFAULT_PROVIDER_ORDER if name in PROVIDERS]


def _order_from_names(raw_names: list[str]) -> list[Provider]:
    ordered: list[Provider] = []
    seen: set[str] = set()

    for raw_name in raw_names:
        if not isinstance(raw_name, str):
            continue
        name = _normalize_provider_name(raw_name)
        if name and name not in seen:
            ordered.append(PROVIDERS[name])
            seen.add(name)

    return ordered


def _load_saved_provider_order() -> list[str] | None:
    if not STATE_FILE.exists():
        return None

    try:
        payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception as error:
        logger.warning("Failed to read AI provider order file: %s", _safe_error(error))
        return None

    raw_order = payload.get("order") if isinstance(payload, dict) else payload
    if not isinstance(raw_order, list):
        return None

    normalized: list[str] = []
    seen: set[str] = set()
    for raw_name in raw_order:
        if not isinstance(raw_name, str):
            continue
        name = _normalize_provider_name(raw_name)
        if name and name not in seen:
            normalized.append(name)
            seen.add(name)

    return normalized or None


def _save_provider_order(order: list[str]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "order": order,
        "updated_at": time.time(),
    }
    tmp_file = STATE_FILE.with_suffix(".tmp")
    tmp_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_file.replace(STATE_FILE)


def _call_openai(system_prompt: str, user_content: str, api_key: str, model: str, timeout: float) -> dict:
    from openai import OpenAI

    # Cliente criado por chamada (chave pode ser rotacionada em runtime pelo
    # painel admin) — `with` fecha o pool de conexoes httpx no final, senao
    # o fechamento fica a merce do GC e pode vazar file descriptors sob
    # carga (accept()/socket nao liberado -> OSError: Too many open files).
    with OpenAI(api_key=api_key, timeout=timeout) as client:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
    return _extract_json(response.choices[0].message.content)


def _call_deepseek(system_prompt: str, user_content: str, api_key: str, model: str, timeout: float) -> dict:
    from openai import OpenAI

    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    with OpenAI(api_key=api_key, base_url=base_url, timeout=timeout) as client:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
    return _extract_json(response.choices[0].message.content)


def _call_anthropic(system_prompt: str, user_content: str, api_key: str, model: str, timeout: float) -> dict:
    import anthropic

    with anthropic.Anthropic(api_key=api_key, timeout=timeout) as client:
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=(
                f"{system_prompt}\n\n"
                "Responda apenas com JSON valido, sem markdown e sem texto adicional."
            ),
            messages=[{"role": "user", "content": user_content}],
        )
    # content[0] nem sempre e texto: alguns modelos (ex.: claude-sonnet-5)
    # podem antepor blocos de outro tipo (ex.: thinking) antes do texto.
    texto = next((b.text for b in response.content if getattr(b, "type", None) == "text"), None)
    if texto is None:
        raise RuntimeError(f"Resposta da Anthropic sem bloco de texto: {response.content!r}")
    return _extract_json(texto)


def _call_gemini(system_prompt: str, user_content: str, api_key: str, model: str, timeout: float) -> dict:
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    gemini_model = genai.GenerativeModel(
        model_name=model,
        system_instruction=system_prompt,
        generation_config={
            "response_mime_type": "application/json",
            "temperature": 0.3,
        },
    )
    response = gemini_model.generate_content(
        user_content,
        request_options={"timeout": timeout},
    )
    return _extract_json(response.text)


PROVIDERS: dict[str, Provider] = {
    "deepseek": Provider(
        name="deepseek",
        env_keys=("DEEPSEEK_API_KEY",),
        model_env="DEEPSEEK_MODEL",
        default_model="deepseek-chat",
        caller=_call_deepseek,
    ),
    "openai": Provider(
        name="openai",
        env_keys=("OPENAI_API_KEY",),
        model_env="OPENAI_MODEL",
        default_model="gpt-4o",
        caller=_call_openai,
    ),
    "anthropic": Provider(
        name="anthropic",
        env_keys=("ANTHROPIC_API_KEY",),
        model_env="ANTHROPIC_MODEL",
        default_model="claude-sonnet-4-20250514",
        caller=_call_anthropic,
    ),
    "gemini": Provider(
        name="gemini",
        env_keys=("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        model_env="GEMINI_MODEL",
        default_model="gemini-2.0-flash",
        caller=_call_gemini,
    ),
}

_breakers: dict[str, CircuitBreaker] = {
    name: CircuitBreaker(name) for name in PROVIDERS
}

# ─────────────────────────────────────────────
# MÉTRICAS EM MEMÓRIA — Fase 2 Observabilidade
# ─────────────────────────────────────────────
_counters_lock = threading.Lock()
_counters: dict = {
    "chamadas_total": 0,
    "chamadas_sucesso": 0,
    "chamadas_falha": 0,
    "fallbacks": 0,
    "circuit_breaker_aberturas": 0,
    "custo_total_usd": 0.0,
    "por_provedor": {
        name: {"sucesso": 0, "falha": 0, "total_ms": 0, "custo_usd": 0.0}
        for name in ("deepseek", "openai", "anthropic", "gemini")
    },
    "inicio": time.time(),
}


def _provider_order() -> list[Provider]:
    saved_order = _load_saved_provider_order()
    if saved_order:
        ordered = _order_from_names(saved_order)
        if ordered:
            return ordered

    raw_order = os.getenv("AI_PROVIDER_ORDER", ",".join(DEFAULT_PROVIDER_ORDER))
    ordered = _order_from_names(raw_order.split(","))
    if ordered:
        return ordered

    return [PROVIDERS[name] for name in _default_provider_names()]


def _api_key(provider: Provider) -> str | None:
    for env_key in provider.env_keys:
        value = os.getenv(env_key)
        if value:
            return value
    return None


def _model(provider: Provider) -> str:
    return os.getenv(provider.model_env, provider.default_model)


def _safe_error(error: Exception) -> str:
    message = f"{type(error).__name__}: {error}"
    message = re.sub(r"sk-[A-Za-z0-9_\-]+", "[redacted]", message)
    message = re.sub(r"(?i)(api[_-]?key|token|password|secret)=\S+", r"\1=[redacted]", message)
    message = re.sub(r"(?i)(authorization|bearer)\s+[A-Za-z0-9_\-\.]+", r"\1 [redacted]", message)
    if len(message) > ERROR_MAX_LENGTH:
        message = f"{message[:ERROR_MAX_LENGTH]}..."
    return message


def _estimate_token_count(text: str) -> int:
    text = text or ""
    if not text:
        return 0
    return max(1, int(round(len(text) / 4)))


def _estimate_call_cost(provider_name: str, system_prompt: str, user_content: str, result: dict) -> dict:
    provider_name = provider_name if provider_name in ESTIMATED_COST_INPUT_PER_MILLION else "openai"
    prompt_text = f"{system_prompt or ''}\n{user_content or ''}"
    output_text = json.dumps(result or {}, ensure_ascii=False)
    input_tokens = _estimate_token_count(prompt_text)
    output_tokens = _estimate_token_count(output_text)
    input_rate = ESTIMATED_COST_INPUT_PER_MILLION.get(provider_name, ESTIMATED_COST_INPUT_PER_MILLION["openai"])
    output_rate = ESTIMATED_COST_OUTPUT_PER_MILLION.get(provider_name, ESTIMATED_COST_OUTPUT_PER_MILLION["openai"])
    estimated_cost = ((input_tokens * input_rate) + (output_tokens * output_rate)) / 1_000_000
    return {
        "_custo_estimado_ia": round(estimated_cost, 6),
        "_moeda_ia": "USD",
        "_tokens_entrada_ia": input_tokens,
        "_tokens_saida_ia": output_tokens,
    }


def _status_label(provider: Provider) -> str:
    breaker = _breakers[provider.name]
    if not _api_key(provider):
        return "sem_chave"
    if not breaker.available:
        remaining = max(0, COOLDOWN_SECONDS - (time.time() - breaker.opened_at))
        return f"cooldown_{int(remaining)}s"
    if breaker.failures > 0:
        return f"degradado_{breaker.failures}_falhas"
    return "ok"


def ordem_provedores() -> list[str]:
    return [provider.name for provider in _provider_order()]


def snapshot_provedores() -> dict:
    ordem = ordem_provedores()
    return {
        "ia": status_provedores(),
        "ordem_ia": ordem,
        "provedor_preferido": ordem[0] if ordem else None,
    }


def snapshot_metricas() -> dict:
    """Retorna cópia thread-safe dos contadores de uso da IA desde o último restart."""
    with _counters_lock:
        snap = {
            "chamadas_total": _counters["chamadas_total"],
            "chamadas_sucesso": _counters["chamadas_sucesso"],
            "chamadas_falha": _counters["chamadas_falha"],
            "fallbacks": _counters["fallbacks"],
            "circuit_breaker_aberturas": _counters["circuit_breaker_aberturas"],
            "custo_total_usd": round(_counters["custo_total_usd"], 6),
            "uptime_segundos": int(time.time() - _counters["inicio"]),
            "por_provedor": {
                name: dict(stats)
                for name, stats in _counters["por_provedor"].items()
            },
        }
    for stats in snap["por_provedor"].values():
        stats["latencia_media_ms"] = (
            round(stats["total_ms"] / stats["sucesso"]) if stats["sucesso"] > 0 else None
        )
        stats["custo_usd"] = round(stats["custo_usd"], 6)
    return snap


def chamar_ia(system_prompt: str, user_content: str) -> dict:
    """
    Calls the configured AI providers in order until one returns valid JSON.

    Raises HTTP 503 only after every configured and available provider fails.
    """
    attempts: list[dict] = []
    system_prompt = f"{system_prompt or ''}{FORBIDDEN_TRIGGER_RULE}"

    with _counters_lock:
        _counters["chamadas_total"] += 1

    for provider in _provider_order():
        breaker = _breakers[provider.name]
        model = _model(provider)

        if not breaker.available:
            attempts.append({"provider": provider.name, "status": "cooldown"})
            logger.info("Skipping %s because its circuit breaker is open", provider.name)
            continue

        key = _api_key(provider)
        if not key:
            attempts.append({"provider": provider.name, "status": "missing_api_key"})
            with _counters_lock:
                _counters["por_provedor"][provider.name]["falha"] += 1
            logger.warning("Skipping %s: API key not configured", provider.name)
            continue

        started_at = time.perf_counter()
        try:
            logger.info("Trying AI provider %s with model %s", provider.name, model)
            result = provider.caller(
                system_prompt,
                user_content,
                key,
                model,
                DEFAULT_TIMEOUT_SECONDS,
            )
            result = _sanitize_ai_payload(result)
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            metrica_custo = _estimate_call_cost(provider.name, system_prompt, user_content, result)
            breaker.register_success()
            attempts.append({
                "provider": provider.name,
                "model": model,
                "status": "success",
                "latency_ms": elapsed_ms,
                "custo_estimado_usd": metrica_custo["_custo_estimado_ia"],
            })

            failed_before = sum(1 for a in attempts[:-1] if a.get("status") == "failed")
            custo = metrica_custo["_custo_estimado_ia"]
            with _counters_lock:
                _counters["chamadas_sucesso"] += 1
                _counters["custo_total_usd"] += custo
                _counters["por_provedor"][provider.name]["sucesso"] += 1
                _counters["por_provedor"][provider.name]["total_ms"] += elapsed_ms
                _counters["por_provedor"][provider.name]["custo_usd"] += custo
                if failed_before > 0:
                    _counters["fallbacks"] += 1

            result.setdefault("_provedor_ia", provider.name)
            result.setdefault("_modelo_ia", model)
            result.setdefault("_tentativas_ia", attempts)
            result.setdefault("_custo_estimado_ia", metrica_custo["_custo_estimado_ia"])
            result.setdefault("_moeda_ia", metrica_custo["_moeda_ia"])
            result.setdefault("_tokens_entrada_ia", metrica_custo["_tokens_entrada_ia"])
            result.setdefault("_tokens_saida_ia", metrica_custo["_tokens_saida_ia"])
            return result

        except Exception as error:
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            breaker.register_failure()
            safe_error = _safe_error(error)
            attempts.append({
                "provider": provider.name,
                "model": model,
                "status": "failed",
                "latency_ms": elapsed_ms,
                "error": safe_error,
            })
            logger.warning("AI provider %s failed: %s", provider.name, safe_error)
            with _counters_lock:
                _counters["por_provedor"][provider.name]["falha"] += 1

    logger.error("All AI providers failed or were unavailable: %s", attempts)
    with _counters_lock:
        _counters["chamadas_falha"] += 1
    raise HTTPException(
        status_code=503,
        detail={
            "erro": "Servico de IA temporariamente indisponivel. Tente novamente em instantes.",
            "provedores_tentados": attempts,
        },
    )


def rotacionar_provedor_preferido() -> dict:
    ordem_atual = ordem_provedores()
    if not ordem_atual:
        raise HTTPException(
            status_code=503,
            detail={"erro": "Nenhum provedor de IA configurado."},
        )

    if len(ordem_atual) == 1:
        snapshot = snapshot_provedores()
        return {
            "status": "online",
            "mensagem": "Apenas um provedor de IA esta configurado; nenhuma troca foi necessaria.",
            **snapshot,
        }

    nova_ordem = ordem_atual[1:] + ordem_atual[:1]
    _save_provider_order(nova_ordem)
    logger.info("AI provider order rotated to %s", nova_ordem)
    snapshot = snapshot_provedores()
    return {
        "status": "online",
        "mensagem": f"Provedor preferido alterado para {nova_ordem[0]}.",
        **snapshot,
    }


def definir_provedor_preferido(provedor: str) -> dict:
    nome = _normalize_provider_name(provedor or "")
    if not nome:
        raise HTTPException(
            status_code=400,
            detail={"erro": "Provedor de IA invalido ou nao suportado."},
        )

    ordem_atual = ordem_provedores()
    if not ordem_atual:
        ordem_atual = _default_provider_names()

    nova_ordem = [nome] + [item for item in ordem_atual if item != nome]
    _save_provider_order(nova_ordem)
    logger.info("AI provider order set to %s", nova_ordem)
    snapshot = snapshot_provedores()
    return {
        "status": "online",
        "mensagem": f"Provedor preferido definido para {nova_ordem[0]}.",
        **snapshot,
    }


async def chamar_ia_async(system_prompt: str, user_content: str) -> dict:
    """Async wrapper for FastAPI paths and async agents."""
    return await asyncio.to_thread(chamar_ia, system_prompt, user_content)


def status_provedores() -> dict:
    """Returns the operational state of each configured provider without secrets."""
    return {
        provider.name: {
            "status": _status_label(provider),
            "modelo": _model(provider),
            "configurado": bool(_api_key(provider)),
            "falhas_consecutivas": _breakers[provider.name].failures,
        }
        for provider in _provider_order()
    }


def resetar_estado_ia_para_testes() -> None:
    """Clears in-memory circuit breaker state for unit tests."""
    for breaker in _breakers.values():
        breaker.register_success()
