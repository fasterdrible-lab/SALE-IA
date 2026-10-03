"""
SALEIA — agent/intelligence_version_rules.py

Tarefa D6 de docs/tasks-prompt-mestre-v2-restante.md (seção 34 do prompt
mestre, "qual versão recomendou isso"): as 4 versões que acompanham cada
`RecommendationEvent` e `AuditTrailEntry`, além das `prompt_version`/
`rule_version` que já existiam.

Decisão central: versão **derivada do conteúdo**, nunca número digitado
à mão. Uma string manual (como o `_PROMPT_VERSION = "...v1"` do motor)
fica igual quando alguém esquece de mudar; um hash do que de fato rodou
muda sozinho. Formato `nome@<10 hex>`.

- `reasoning_engine_version`: quem gerou a recomendação —
  `sales_reasoning_engine@…` (prompt do motor + versão da regra) quando
  o Piloto foi aplicado; `multiagente@…` (os 5 prompts do multiagente)
  no caminho atual.
- `policy_version`: guardas de prompt aplicadas em toda chamada de IA
  (regra de gatilhos proibidos, anti-injection, adversarial) + tabela de
  fronteiras da AutonomyPolicy e o limite de desconto.
- `knowledge_version`: estado do conhecimento curado que entra no
  contexto — quantidade e última atualização dos KnowledgeItems
  APPROVED + provedor/modelo de embedding. Cache de 5 min (consulta ao
  banco). A base RAG legada (`base_conhecimento`, pymysql cru) fica de
  fora — limitação documentada.
- `model_version`: `provedor/modelo` da última chamada real da feature
  na reunião (`AiUsageEvent`). `None` quando não há chamada registrada.

Tudo é melhor esforço: uma versão que não puder ser calculada vira
`None`, nunca derruba a gravação da recomendação/auditoria.
"""

import hashlib
import logging
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_TEMPLATES = Path(__file__).parent / "prompt_templates"
_TEMPLATES_MULTIAGENTE = (
    "multiagente_coach.txt", "multiagente_disc.txt", "multiagente_finance.txt",
    "multiagente_closer.txt", "multiagente_bigfive.txt",
)
ORIGEM_MOTOR = "sales_reasoning_engine"
ORIGEM_MULTIAGENTE = "multiagente"

_TTL_KNOWLEDGE_S = 300
_cache_knowledge = {"valor": None, "em": 0.0}


def versao_de_conteudo(nome: str, *partes) -> str:
    """`nome@<10 hex>` — sha256 das partes (texto) concatenadas."""
    h = hashlib.sha256()
    for parte in partes:
        h.update(str(parte).encode("utf-8"))
        h.update(b"\x00")
    return f"{nome}@{h.hexdigest()[:10]}"


def _ler(arquivo: str) -> str:
    try:
        return (_TEMPLATES / arquivo).read_text(encoding="utf-8")
    except OSError:
        return f"<ausente:{arquivo}>"


@lru_cache(maxsize=4)
def reasoning_engine_version(origem: str = ORIGEM_MULTIAGENTE) -> str:
    """Cacheado por processo: os templates só mudam com deploy (que
    reinicia o serviço)."""
    if origem == ORIGEM_MOTOR:
        from agent.sales_reasoning_engine import _RULE_VERSION
        return versao_de_conteudo(ORIGEM_MOTOR, _ler("sales_reasoning_engine.txt"), _RULE_VERSION)
    return versao_de_conteudo(ORIGEM_MULTIAGENTE, *(_ler(t) for t in _TEMPLATES_MULTIAGENTE))


@lru_cache(maxsize=1)
def policy_version() -> str:
    from agent.adversarial_sales_rules import ADVERSARIAL_SALES_GUARD_TEXT
    from agent.autonomy_policy_rules import DECISION_BOUNDARIES_PADRAO, LIMITE_DESCONTO_POLICY_DEPENDENT_PADRAO
    from agent.prompt_injection_rules import PROMPT_INJECTION_GUARD_TEXT
    from api.ai_router import FORBIDDEN_TRIGGER_RULE

    fronteiras = sorted((str(k), str(v)) for k, v in DECISION_BOUNDARIES_PADRAO.items())
    return versao_de_conteudo(
        "policy", FORBIDDEN_TRIGGER_RULE, PROMPT_INJECTION_GUARD_TEXT, ADVERSARIAL_SALES_GUARD_TEXT,
        fronteiras, LIMITE_DESCONTO_POLICY_DEPENDENT_PADRAO,
    )


def _embedding_config() -> str:
    provider = os.environ.get("EMBEDDING_PROVIDER", "ollama").strip().lower()
    if provider == "openai":
        modelo = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    else:
        modelo = os.environ.get("OLLAMA_EMBEDDING_MODEL", "embeddinggemma")
    return f"{provider}/{modelo}"


def knowledge_version(agora: Optional[float] = None) -> Optional[str]:
    agora = time.monotonic() if agora is None else agora
    if _cache_knowledge["valor"] and agora - _cache_knowledge["em"] < _TTL_KNOWLEDGE_S:
        return _cache_knowledge["valor"]
    try:
        from sqlmodel import Session, select
        from sqlalchemy import func

        from api.database import KnowledgeItem, engine

        with Session(engine) as session:
            total, ultima = session.exec(
                select(func.count(KnowledgeItem.id), func.max(KnowledgeItem.updated_at))
                .where(KnowledgeItem.status == "APPROVED")
            ).one()
        valor = versao_de_conteudo("knowledge", total, ultima.isoformat() if ultima else None, _embedding_config())
    except Exception as e:
        logger.debug("[Versionamento] knowledge_version indisponível: %s", e)
        return None
    _cache_knowledge.update(valor=valor, em=agora)
    return valor


def resetar_cache_para_testes() -> None:
    _cache_knowledge.update(valor=None, em=0.0)
    reasoning_engine_version.cache_clear()
    policy_version.cache_clear()


def model_version(provider: Optional[str], model: Optional[str]) -> Optional[str]:
    if not provider and not model:
        return None
    return f"{provider or '?'}/{model or '?'}"


def versoes_da_inteligencia(
    origem: str = ORIGEM_MULTIAGENTE,
    *,
    feature: Optional[str] = None,
    meeting_id: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> dict:
    """As 4 versões. `provider`/`model` explícitos vencem; sem eles,
    busca a última chamada real de `feature` na reunião."""
    versoes = {}
    for chave, calcular in (
        ("reasoning_engine_version", lambda: reasoning_engine_version(origem)),
        ("policy_version", policy_version),
        ("knowledge_version", knowledge_version),
    ):
        try:
            versoes[chave] = calcular()
        except Exception as e:
            logger.debug("[Versionamento] %s indisponível: %s", chave, e)
            versoes[chave] = None

    if not (provider or model) and feature and meeting_id:
        try:
            from api.database import obter_ultimo_ai_usage_event
            evento = obter_ultimo_ai_usage_event(feature, meeting_id) or {}
            provider, model = evento.get("provider"), evento.get("model")
        except Exception as e:
            logger.debug("[Versionamento] model_version indisponível: %s", e)
    versoes["model_version"] = model_version(provider, model)
    return versoes
