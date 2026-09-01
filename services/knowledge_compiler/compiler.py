"""
services/knowledge_compiler/compiler.py — Knowledge Compiler Fase 2:
compilação com IA das seções extraídas na Fase 1 em KnowledgeItems
estruturados (frameworks, objeções, scripts, etc.).

Fluxo: KnowledgeSource (com sections da Fase 1) -> 1 chamada de IA por
seção não sinalizada -> validação -> dedup por embedding -> persistência
como DRAFT. Nenhum item entra em uso (RAG/Skills/Playbook — Fase 3) sem
aprovação humana.
"""
import json
import logging
from pathlib import Path
from typing import Optional

from api import ai_features
from api.ai_router import chamar_ia_async, status_provedores
from api.cost_engine import ProviderUsage, calcular_custo
from api.database import (
    buscar_knowledge_item_similar,
    criar_knowledge_item,
    salvar_embedding_knowledge_item,
)
from services.knowledge_compiler.sanitizer import INJECTION_FLAG

logger = logging.getLogger("saleia.knowledge_compiler")

KNOWLEDGE_ITEM_TYPES = {
    "FRAMEWORK", "OBJECTION", "DISCOVERY_QUESTION", "SCRIPT",
    "ANTI_PATTERN", "DECISION_RULE", "CASE",
}

_PROMPT_PATH = Path(__file__).parent.parent.parent / "agent" / "prompt_templates" / "knowledge_compiler_extracao.txt"
_PROMPT_TEMPLATE: Optional[str] = None

# Heurística de estimativa (pré-voo, sem chamar IA): tokens de saída
# esperados por seção — resposta JSON compacta com poucos itens.
_TOKENS_SAIDA_ESTIMADOS_POR_SECAO = 400


def _get_prompt() -> str:
    global _PROMPT_TEMPLATE
    if _PROMPT_TEMPLATE is None:
        _PROMPT_TEMPLATE = _PROMPT_PATH.read_text(encoding="utf-8")
    return _PROMPT_TEMPLATE


def _provedor_e_modelo_atuais() -> tuple[str, str]:
    status = status_provedores()
    provedor = next(iter(status), "deepseek")
    modelo = status.get(provedor, {}).get("modelo") or "deepseek-chat"
    return provedor, modelo


def _secoes_compilaveis(fonte: dict) -> tuple[list[dict], list[dict]]:
    """Separa as seções da fonte em (compilaveis, puladas) — puladas são
    as sinalizadas pelo sanitizer da Fase 1 (potential_instruction_injection)."""
    secoes = fonte.get("sections") or []
    compilaveis, puladas = [], []
    for secao in secoes:
        if INJECTION_FLAG in (secao.get("flags") or []):
            puladas.append(secao)
        else:
            compilaveis.append(secao)
    return compilaveis, puladas


def estimar_custo_compilacao(fonte: dict) -> dict:
    """Estimativa pré-voo, sem nenhuma chamada de IA — usada para mostrar
    ao usuário antes de gastar dinheiro de verdade (Tarefa 33 da spec)."""
    compilaveis, puladas = _secoes_compilaveis(fonte)
    provedor, modelo = _provedor_e_modelo_atuais()

    prompt_base_chars = len(_get_prompt())
    total_input_chars = sum(prompt_base_chars + len(s.get("content", "")) for s in compilaveis)
    input_tokens = max(1, round(total_input_chars / 4))
    output_tokens = len(compilaveis) * _TOKENS_SAIDA_ESTIMADOS_POR_SECAO

    usage = ProviderUsage(input_tokens=input_tokens, output_tokens=output_tokens)
    custo = calcular_custo(provedor, modelo, usage, usage_source="estimated")

    return {
        "secoes_a_compilar": len(compilaveis),
        "secoes_puladas": len(puladas),
        "provedor_estimado": provedor,
        "modelo_estimado": modelo,
        "tokens_entrada_estimados": input_tokens,
        "tokens_saida_estimados": output_tokens,
        "custo_estimado_usd": custo.cost_usd,
        "aviso": "Estimativa baseada no provedor preferido atual — o custo real pode variar se houver fallback entre provedores.",
    }


def _validar_item(candidato: dict) -> Optional[dict]:
    if not isinstance(candidato, dict):
        return None
    item_type = str(candidato.get("type", "")).strip().upper()
    if item_type not in KNOWLEDGE_ITEM_TYPES:
        return None
    title = str(candidato.get("title") or "").strip()[:255]
    content = str(candidato.get("content") or "").strip()
    if not title or not content or len(content) < 20:
        return None

    try:
        confidence = max(0.0, min(1.0, float(candidato.get("confidence", 0.75))))
    except (TypeError, ValueError):
        confidence = 0.75

    tags = candidato.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    metadata = candidato.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    return {
        "item_type": item_type,
        "title": title,
        "content": content,
        "confidence": confidence,
        "tags": [str(t).strip() for t in tags if t][:10],
        "metadata": metadata,
    }


async def _compilar_secao(secao: dict, source_id: Optional[int]) -> list[dict]:
    prompt = _get_prompt().replace("{titulo_secao}", secao.get("title", "")).replace(
        "{conteudo_secao}", secao.get("content", "")
    )
    try:
        resposta = await chamar_ia_async(
            system_prompt=prompt,
            user_content="Extraia o conhecimento comercial desta seção.",
            feature=ai_features.KNOWLEDGE_COMPILER_EXTRACAO,
            meeting_id=f"knowledge_source:{source_id}" if source_id else None,
        )
    except Exception as e:
        logger.warning("[KnowledgeCompiler] Erro ao compilar seção '%s': %s", secao.get("title"), e)
        return []

    candidatos = resposta.get("itens", []) if isinstance(resposta, dict) else []
    validados = [v for c in candidatos if (v := _validar_item(c))]
    logger.info(
        "[KnowledgeCompiler] Seção '%s': %d itens válidos de %d candidatos",
        secao.get("title"), len(validados), len(candidatos),
    )
    return validados


async def compilar_fonte(source_id: int, fonte: dict) -> dict:
    """Orquestra a compilação completa de uma fonte já EXTRACTED: 1
    chamada de IA por seção compilável, validação, dedup por embedding e
    persistência em lote. `fonte` é o dict de KnowledgeSource já carregado
    (incluir_texto=True) pelo chamador — evita releitura redundante."""
    compilaveis, puladas = _secoes_compilaveis(fonte)

    todos_itens: list[dict] = []
    for secao in compilaveis:
        todos_itens.extend(await _compilar_secao(secao, source_id))

    if not todos_itens:
        return {
            "itens_criados": 0, "por_tipo": {}, "secoes_compiladas": len(compilaveis),
            "secoes_puladas": len(puladas),
        }

    from services.embeddings import get_embedding_provider

    try:
        provider = get_embedding_provider()
    except Exception as e:
        logger.warning("[KnowledgeCompiler] Provedor de embedding indisponível — itens salvos sem dedup: %s", e)
        provider = None

    criados: list[dict] = []
    for item in todos_itens:
        resultado = None
        if provider is not None:
            resultado = await provider.embed_async(item["content"][:6000])
            if resultado:
                similar = buscar_knowledge_item_similar(item["item_type"], resultado.vector)
                if similar:
                    item["possivel_duplicado_de"] = similar["id"]

        item_criado = criar_knowledge_item(source_id, item)
        if not item_criado:
            continue
        criados.append(item_criado)
        if resultado:
            salvar_embedding_knowledge_item(
                item_criado["id"], resultado.vector,
                resultado.provider, resultado.model, resultado.dimension,
            )

    por_tipo: dict = {}
    for item in criados:
        por_tipo[item["item_type"]] = por_tipo.get(item["item_type"], 0) + 1

    return {
        "itens_criados": len(criados),
        "por_tipo": por_tipo,
        "secoes_compiladas": len(compilaveis),
        "secoes_puladas": len(puladas),
    }
