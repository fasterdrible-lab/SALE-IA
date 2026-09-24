"""
T5.5 — Orquestrador Multiagente.

Roda Coach, DISC, Finance e Closer em paralelo via asyncio.gather e
consolida os resultados no mesmo schema JSON que o agente único produzia,
mantendo compatibilidade total com a extensão Chrome e o dashboard.
"""

import asyncio
import logging
import os

from agent.base_conhecimento import buscar_contexto_similar
from agent.multiagente.coach_agent import analisar_coach
from agent.multiagente.disc_agent import analisar_disc
from agent.multiagente.finance_agent import analisar_finance
from agent.multiagente.closer_agent import analisar_closer
from agent.multiagente.bigfive_agent import analisar_bigfive
from agent.propensao_rules import classificar_propensao

logger = logging.getLogger(__name__)


def bigfive_agent_ativo() -> bool:
    """Kill-switch do agente Big Five (5o agente em tempo real, +1 chamada
    de IA por ciclo). `false` no .env + restart volta a rodar so os 4
    agentes originais, sem custo do Big Five — mesmo padrao de todo
    kill-switch ja usado no projeto (Cost Router, Otimizacao, Knowledge
    Compiler)."""
    return os.getenv("BIGFIVE_AGENT_ENABLED", "true").strip().lower() != "false"


def shadow_mode_ativo() -> bool:
    """Kill-switch da Fase 23 ("PROMPT MESTRE — SALE-IA V2") — Teste em
    Shadow Mode: roda `agent/sales_reasoning_engine.py::raciocinar_
    async()` (Fase 7) silenciosamente em paralelo ao modelo atual, sem
    nunca influenciar o que o vendedor vê (`resultado` já foi calculado
    e devolvido antes da task de shadow mode sequer começar). `false`
    por padrão, diferente do Big Five — liga soma **1 chamada real de
    IA por ciclo de tempo real** (mesma ordem de grandeza de custo do
    Big Five, mas aqui o objetivo é só medir, não entregar valor
    imediato ao vendedor), então é opt-in explícito, não default
    ligado. `true` no `.env` + restart ativa; `false` volta a nada
    rodar, sem reverter deploy — mesmo padrão de todo kill-switch já
    usado no projeto."""
    return os.getenv("SHADOW_MODE_ENABLED", "false").strip().lower() == "true"


def pilot_mode_atual() -> str:
    """Feature flag obrigatória da Fase 24 ("PROMPT MESTRE — SALE-IA
    V2", Piloto) — controla se `raciocinar_async()` (Fase 7) passa a
    **influenciar de verdade** a recomendação que um vendedor real vê
    (diferente de `shadow_mode_ativo()`, que nunca influencia nada).
    `PILOT_MODE` no `.env`: `off` (padrão) / `pilot_user` / `5pct` /
    `20pct` / `50pct` / `100pct` — ver `agent/pilot_rollout_rules.py`.
    Rollback funciona sem deploy: `PILOT_MODE=off` + restart volta
    100% pro modelo atual pra todo mundo, mesmo padrão de todo
    kill-switch já usado no projeto. Valor desconhecido no `.env` cai
    em `off` (fail-safe — nunca arrisca interpretar um typo como
    rollout maior do que o pretendido)."""
    from agent.pilot_rollout_rules import PILOT_MODES
    modo = os.getenv("PILOT_MODE", "off").strip().lower()
    return modo if modo in PILOT_MODES else "off"


def recommendation_tracking_ativo() -> bool:
    """Kill-switch das Tarefas 10.1+10.2 ("PROMPT MESTRE — SALE-IA V2",
    Fase 10) ligadas em produção: grava `RecommendationEvent` quando a
    recomendação muda de ciclo pra ciclo, e classifica o uso da
    recomendação pendente anterior contra a fala nova do vendedor via
    embeddings locais (Ollama, mesmo provedor do RAG/Sales Memory — sem
    custo de IA real, diferente do Shadow Mode/SellerDNA Observação).
    `true` por padrão — `false` no `.env` + restart desliga sem
    reverter deploy, mesmo padrão de todo kill-switch já usado no
    projeto."""
    return os.getenv("RECOMMENDATION_TRACKING_ENABLED", "true").strip().lower() != "false"


async def _rastrear_recomendacao(
    resultado: dict,
    transcricao_nova: str,
    meeting_id: str | None,
) -> None:
    """Fase 10 (Tarefas 10.1+10.2) — 2 passos por ciclo, nesta ordem:

    1. Se existe uma `RecommendationEvent` PENDENTE desta reunião
       (`used_at is None` — a última recomendação registrada, ainda sem
       reação do vendedor) e o ciclo trouxe fala nova, classifica o uso
       (`detectar_uso_recomendacao()`, Tarefa 10.2) e grava
       `seller_action` (`registrar_uso_recommendation_event()`, Tarefa
       10.1) — a classificação em si nunca vira coluna nova (mesmo
       princípio de `outcome_rules.calcular_cycle_days()`: sempre
       derivável sob demanda a partir de `recommendation`+
       `seller_action`), só é logada para visibilidade imediata.
    2. Se a recomendação ATUAL (`resultado["next_best_action"]`, já
       pós-Piloto — o que o vendedor de fato vê) é diferente da última
       registrada, cria uma `RecommendationEvent` nova, que vira a
       pendente do próximo ciclo.

    **`transcricao_nova` (achado real, Fase 25 — medindo
    recommendation_quality, 23/09/2026), não `transcricao_parcial`**:
    a versão anterior usava `transcricao_parcial` (o transcript
    ACUMULADO da reunião inteira, limitado a 6.000 chars por
    `_limitar_contexto_ia()`) como `seller_action` — comparar a
    recomendação contra um blob de até 6.000 chars (múltiplos tópicos,
    não só a reação ao que foi recomendado) diluía a similaridade de
    embedding sistematicamente, mascarando classificações `USED` reais
    como `PARTIALLY_USED`/`IGNORED`. `transcricao_nova` é o delta real
    ("apenas novas entradas", já enviado pela extensão desde sempre —
    `chrome-extension/content.js`) — representa literalmente a fala
    nova do vendedor desde o ciclo anterior, o dado certo pra saber se
    ele reagiu à recomendação pendente.

    Best-effort absoluto (mesma disciplina de Shadow Mode/Prompt
    Injection) — nunca pode atrasar nem quebrar o ciclo real; reunião
    anônima (`meeting_id` ausente/`"default"`, mesmo padrão de
    `/audio-transcricao`) nunca grava nada."""
    if not meeting_id or meeting_id == "default" or not recommendation_tracking_ativo():
        return
    try:
        from agent.recommendation_usage_rules import detectar_uso_recomendacao
        from api.database import criar_recommendation_event, listar_recommendation_events, registrar_uso_recommendation_event

        eventos = listar_recommendation_events(meeting_id=meeting_id)
        ultimo = eventos[-1] if eventos else None

        if ultimo and ultimo.get("used_at") is None and (transcricao_nova or "").strip():
            try:
                classificacao = await detectar_uso_recomendacao(ultimo["recommendation"], transcricao_nova)
                registrar_uso_recommendation_event(ultimo["id"], seller_action=transcricao_nova)
                logger.info(
                    "[RecommendationTracking] meeting=%s event=%s estado=%s similaridade=%s",
                    meeting_id, ultimo["id"], classificacao["state"], classificacao.get("similarity"),
                )
            except Exception as _e:
                logger.debug("[RecommendationTracking] Falha ao classificar uso (melhor esforço): %s", _e)

        nba = resultado.get("next_best_action") or {}
        texto = (nba.get("message") or "").strip()
        if texto and (not ultimo or ultimo.get("recommendation") != texto):
            criar_recommendation_event(
                meeting_id=meeting_id,
                strategy=nba.get("category") or "generico",
                recommendation=texto,
                reason=nba.get("reason") or "sem motivo informado",
            )
    except Exception as _e:
        logger.debug("[RecommendationTracking] Falha (melhor esforço): %s", _e)


def pilot_usuarios() -> frozenset:
    """Allowlist usada só quando `pilot_mode_atual() == "pilot_user"` —
    `PILOT_USER_IDS` no `.env`, `usuario_id` separados por vírgula
    (o primeiro vendedor do rollout gradual da Fase 24: "liberar
    inicialmente para 1 vendedor")."""
    bruto = os.getenv("PILOT_USER_IDS", "")
    return frozenset(x.strip() for x in bruto.split(",") if x.strip())


async def _aplicar_piloto_sales_reasoning(
    resultado: dict,
    transcricao_parcial: str,
    historico: str,
    resumo_vivo: str,
    diagnostico_atual: dict,
    mapa_financeiro: dict,
    historico_scores: list,
    eventos: list,
    client_context: str,
    usuario_id: str | None,
    meeting_id: str | None,
) -> None:
    """Fase 24 (Piloto): para um `usuario_id` dentro do rollout,
    substitui de verdade `resultado["next_best_action"]`/`next_best_
    question` pela saída de `raciocinar_async()` (Fase 7) — só aqui o
    motor novo passa a influenciar um vendedor real; em qualquer outro
    ciclo (Shadow Mode ou nenhum dos dois), `resultado` nunca é tocado
    por este módulo. **Fail open**: qualquer falha (da IA ou do
    mapeamento) preserva a recomendação do modelo atual — `resultado`
    só é sobrescrito depois de `raciocinar_async()` retornar com
    sucesso E `mapear_para_next_best_action()` não levantar.

    Diferente de `_rodar_shadow_mode()` (fire-and-forget), esta função
    é sempre `await`ada — o vendedor piloto espera a resposta real do
    motor novo antes de receber o ciclo, então soma latência real de
    +1 chamada de IA aqui (aceito só pra quem está no rollout).

    Reaproveita `agent/shadow_mode_rules.py::montar_registro_shadow()`
    pra persistir a mesma comparação de agreement/latency/cost do
    Shadow Mode, marcada `origem="piloto"` — nunca chama
    `raciocinar_async()` duas vezes no mesmo ciclo pro mesmo vendedor
    (piloto e shadow são mutuamente exclusivos, ver
    `analisar_fragmento_multi()`)."""
    import time as _time

    from agent.objecao_detectada_para_objection_rules import extrair_objecao_do_ciclo
    from agent.pilot_rollout_rules import mapear_para_next_best_action
    from agent.sales_reasoning_engine import raciocinar_async
    from agent.shadow_mode_rules import montar_registro_shadow

    recomendacao_atual = resultado.get("next_best_action") or {}

    # Bloco 1 / Tarefa 1.2 (docs/tasks-sales-reasoning-engine-completo.md):
    # traduz a objeção já detectada pelo Finance (com categoria
    # classificada por IA) pro formato de objection_rules.py — melhor
    # esforço, nunca bloqueia o ciclo se a classificação falhar.
    objections = None
    try:
        objecao = await extrair_objecao_do_ciclo(
            resultado.get("objecao_detectada"), usuario_id=usuario_id, meeting_id=meeting_id,
            transcricao_parcial=transcricao_parcial, historico=historico,
        )
        if objecao:
            objections = [objecao]
    except Exception as _e:
        logger.debug("[Piloto] Falha ao classificar objeção (melhor esforço): %s", _e)

    # Bloco 3 / Tarefa 3.1 + Bloco 2 / Tarefa 2.1 (docs/
    # tasks-sales-reasoning-engine-completo.md): vincula a reunião a
    # uma Opportunity aberta do mesmo cliente quando não há
    # ambiguidade (nunca sobrescreve vínculo existente), depois busca
    # o insight de Win/Loss real do estágio dessa oportunidade —
    # melhor esforço, nunca bloqueia o ciclo.
    #
    # Bloco 6 / Tarefa 6.1 (parcial, docs/
    # tasks-sales-reasoning-engine-completo.md): reaproveita o mesmo
    # opportunity_id já resolvido pra ler OpportunityMemory (Fase 2.1)
    # e OpportunityGraph (Fase 2.2) — leitura pura, zero IA nova, mesmo
    # espírito do Bloco 2. Hoje nada na produção escreve nessas duas
    # estruturas automaticamente, então o valor real costuma vir vazio
    # (`opportunity_memory=None` quando a linha nem existe ainda,
    # `opportunity_graph=[]` quando existe mas sem nenhuma aresta) —
    # vazio real, nunca inventado, mesma disciplina de `spin_state`
    # (Bloco 4.1).
    historical_patterns = None
    opportunity_memory = None
    opportunity_graph = None
    try:
        from agent.historical_pattern_rules import obter_historical_pattern_da_opportunity
        from agent.opportunity_link_rules import vincular_automaticamente_se_possivel
        from api.database import listar_arestas_opportunity, obter_opportunity_memory
        opportunity_id = vincular_automaticamente_se_possivel(meeting_id) if meeting_id else None
        if opportunity_id:
            historical_patterns = obter_historical_pattern_da_opportunity(opportunity_id)
            opportunity_memory = obter_opportunity_memory(opportunity_id, criar_se_ausente=False)
            opportunity_graph = listar_arestas_opportunity(opportunity_id)
    except Exception as _e:
        logger.debug(
            "[Piloto] Falha ao resolver historical_patterns/opportunity_memory/opportunity_graph (melhor esforço): %s", _e,
        )

    # Bloco 4 / Tarefa 4.1 (docs/tasks-sales-reasoning-engine-completo.md):
    # extrai fatos SPIN reais da conversa via IA — melhor esforço,
    # nunca bloqueia o ciclo se a extração falhar.
    spin_state = None
    try:
        from agent.spin_extractor import extrair_spin_state_async
        spin_state = await extrair_spin_state_async(
            transcricao_parcial, historico, usuario_id=usuario_id, meeting_id=meeting_id,
        )
    except Exception as _e:
        logger.debug("[Piloto] Falha ao extrair spin_state (melhor esforço): %s", _e)

    # Bloco 4 / Tarefa 4.2 (docs/tasks-sales-reasoning-engine-completo.md):
    # extrai sinais comportamentais reais da conversa via IA — melhor
    # esforço, nunca bloqueia o ciclo se a extração falhar.
    behavioral_signals = None
    try:
        from agent.behavioral_signal_extractor import extrair_sinais_comportamentais_async
        behavioral_signals = await extrair_sinais_comportamentais_async(
            transcricao_parcial, historico, usuario_id=usuario_id, meeting_id=meeting_id,
        )
    except Exception as _e:
        logger.debug("[Piloto] Falha ao extrair behavioral_signals (melhor esforço): %s", _e)

    # Bloco 4 / Tarefa 4.3 (docs/tasks-sales-reasoning-engine-completo.md):
    # extrai a motivação de compra dominante real da conversa via IA —
    # melhor esforço, nunca bloqueia o ciclo se a extração falhar.
    buyer_motivation = None
    try:
        from agent.buyer_motivation_extractor import extrair_buyer_motivation_async
        buyer_motivation = await extrair_buyer_motivation_async(
            transcricao_parcial, historico, usuario_id=usuario_id, meeting_id=meeting_id,
        )
    except Exception as _e:
        logger.debug("[Piloto] Falha ao extrair buyer_motivation (melhor esforço): %s", _e)

    entrada = {
        "meeting_memory": {
            "transcricao_parcial": transcricao_parcial,
            "historico": historico,
            "resumo_vivo": resumo_vivo,
            "diagnostico_atual": diagnostico_atual,
            "mapa_financeiro": mapa_financeiro,
            "historico_scores": historico_scores,
            "eventos": eventos,
        },
        "rag_context": client_context or None,
        "objections": objections,
        "historical_patterns": historical_patterns,
        "opportunity_memory": opportunity_memory,
        "opportunity_graph": opportunity_graph,
        "spin_state": spin_state,
        "behavioral_signals": behavioral_signals,
        "buyer_motivation": buyer_motivation,
    }

    inicio = _time.monotonic()
    recomendacao_nova = None
    erro = None
    try:
        recomendacao_nova = await raciocinar_async(entrada, usuario_id=usuario_id, meeting_id=meeting_id)
    except Exception as e:
        erro = f"{type(e).__name__}: {e}"
        logger.warning("[Piloto] raciocinar_async falhou, mantendo modelo atual: %s", erro)
    latency_ms = int((_time.monotonic() - inicio) * 1000)

    if recomendacao_nova is not None:
        try:
            nova_nba = mapear_para_next_best_action(recomendacao_nova)
            resultado["next_best_action"] = nova_nba
            resultado["next_best_question"] = _nba_para_nbq(nova_nba)
        except Exception as _e:
            logger.warning("[Piloto] Falha ao aplicar recomendação nova, mantendo modelo atual: %s", _e)

    cost_usd = None
    try:
        from api import ai_features
        from api.database import obter_ultimo_ai_usage_event
        evento = obter_ultimo_ai_usage_event(ai_features.SALES_REASONING_RACIOCINIO, meeting_id)
        if evento:
            cost_usd = evento.get("cost_usd")
    except Exception:
        pass

    registro = montar_registro_shadow(recomendacao_atual, recomendacao_nova, latency_ms, cost_usd, erro)
    try:
        from api.database import criar_shadow_mode_comparison
        criar_shadow_mode_comparison(meeting_id=meeting_id, usuario_id=usuario_id, origem="piloto", **registro)
    except Exception as _e:
        logger.debug("[Piloto] Falha ao persistir comparação (melhor esforço): %s", _e)


# Referencias fortes das tasks de shadow mode em voo — sem isso, o
# event loop do asyncio pode coletar a Task antes dela terminar (nao ha
# nenhuma outra referencia viva depois que analisar_fragmento_multi
# retorna). Removida do set assim que a task termina (add_done_callback).
_SHADOW_MODE_TASKS: set = set()


def _agendar_shadow_mode(
    resultado: dict,
    transcricao_parcial: str,
    historico: str,
    resumo_vivo: str,
    diagnostico_atual: dict,
    mapa_financeiro: dict,
    historico_scores: list,
    eventos: list,
    client_context: str,
    usuario_id: str | None,
    meeting_id: str | None,
) -> None:
    """Dispara a comparação Shadow Mode (Fase 23) como fire-and-forget —
    nunca aguardada pelo ciclo real, nunca pode atrasar a resposta que
    o vendedor recebe. `resultado` já é o dict final que será retornado
    ao chamador; só a recomendação atual (`next_best_action`) é lida
    daqui, nunca mutada."""
    if not shadow_mode_ativo():
        return
    task = asyncio.create_task(_rodar_shadow_mode(
        recomendacao_atual=resultado.get("next_best_action") or {},
        objecao_detectada=resultado.get("objecao_detectada"),
        transcricao_parcial=transcricao_parcial,
        historico=historico,
        resumo_vivo=resumo_vivo,
        diagnostico_atual=diagnostico_atual,
        mapa_financeiro=mapa_financeiro,
        historico_scores=historico_scores,
        eventos=eventos,
        client_context=client_context,
        usuario_id=usuario_id,
        meeting_id=meeting_id,
    ))
    _SHADOW_MODE_TASKS.add(task)
    task.add_done_callback(_SHADOW_MODE_TASKS.discard)


async def _rodar_shadow_mode(
    recomendacao_atual: dict,
    objecao_detectada: dict | None,
    transcricao_parcial: str,
    historico: str,
    resumo_vivo: str,
    diagnostico_atual: dict,
    mapa_financeiro: dict,
    historico_scores: list,
    eventos: list,
    client_context: str,
    usuario_id: str | None,
    meeting_id: str | None,
) -> None:
    """Roda `raciocinar_async()` (Fase 7) silenciosamente e persiste a
    comparação (Fase 23). Melhor esforço absoluto — qualquer exceção
    aqui (inclusive de persistência) nunca pode aparecer pro vendedor
    nem para o ciclo real, que já terminou antes desta função começar
    (chamada via `asyncio.create_task`, nunca `await`ada por
    `analisar_fragmento_multi`)."""
    import time as _time

    from agent.objecao_detectada_para_objection_rules import extrair_objecao_do_ciclo
    from agent.sales_reasoning_engine import raciocinar_async
    from agent.shadow_mode_rules import montar_registro_shadow

    # 9 dos 11 campos do contrato têm dado real hoje no ciclo de
    # tempo real — meeting_memory (subconjunto do estado ao vivo da
    # reunião, nunca o registro completo do banco), rag_context (o
    # mesmo client_context — RAG + Sales Memory + Knowledge Compiler —
    # já usado pelos 4-5 agentes reais), objections (Bloco 1 / Tarefa
    # 1.2 + Bloco 4 / Tarefa 4.4, docs/
    # tasks-sales-reasoning-engine-completo.md — traduz objecao_
    # detectada do Finance, com categoria classificada por IA e
    # investigação de causa raiz real), historical_patterns (Bloco
    # 2/3 / Tarefas 2.1+3.1 — vincula a reunião a uma Opportunity e
    # busca o insight de Win/Loss real do estágio dela),
    # opportunity_memory/opportunity_graph (Bloco 6 / Tarefa 6.1
    # parcial — leitura pura do mesmo opportunity_id já resolvido,
    # zero IA nova; hoje costuma vir vazio porque nada na produção
    # escreve nessas 2 estruturas automaticamente ainda, mas vazio
    # real nunca é fabricado), spin_state (Bloco 4 / Tarefa 4.1 —
    # extrai fatos SPIN reais da conversa via IA), behavioral_signals
    # (Bloco 4 / Tarefa 4.2 — extrai sinais comportamentais reais da
    # conversa via IA) e buyer_motivation (Bloco 4 / Tarefa 4.3 —
    # extrai a motivação de compra dominante real da conversa via IA,
    # fecha o Bloco 4). Os outros 2 (meddpicc_state, seller_context)
    # ficam `None` — meddpicc_state segue bloqueado (Tarefa 1.1, sem
    # citação real disponível no maturity_score do Closer),
    # seller_context depende do Bloco 5 (SellerDNA persistido), ainda
    # não iniciado.
    objections = None
    try:
        objecao = await extrair_objecao_do_ciclo(
            objecao_detectada, usuario_id=usuario_id, meeting_id=meeting_id,
            transcricao_parcial=transcricao_parcial, historico=historico,
        )
        if objecao:
            objections = [objecao]
    except Exception as _e:
        logger.debug("[ShadowMode] Falha ao classificar objeção (melhor esforço): %s", _e)

    historical_patterns = None
    opportunity_memory = None
    opportunity_graph = None
    try:
        from agent.historical_pattern_rules import obter_historical_pattern_da_opportunity
        from agent.opportunity_link_rules import vincular_automaticamente_se_possivel
        from api.database import listar_arestas_opportunity, obter_opportunity_memory
        opportunity_id = vincular_automaticamente_se_possivel(meeting_id) if meeting_id else None
        if opportunity_id:
            historical_patterns = obter_historical_pattern_da_opportunity(opportunity_id)
            opportunity_memory = obter_opportunity_memory(opportunity_id, criar_se_ausente=False)
            opportunity_graph = listar_arestas_opportunity(opportunity_id)
    except Exception as _e:
        logger.debug(
            "[ShadowMode] Falha ao resolver historical_patterns/opportunity_memory/opportunity_graph (melhor esforço): %s", _e,
        )

    spin_state = None
    try:
        from agent.spin_extractor import extrair_spin_state_async
        spin_state = await extrair_spin_state_async(
            transcricao_parcial, historico, usuario_id=usuario_id, meeting_id=meeting_id,
        )
    except Exception as _e:
        logger.debug("[ShadowMode] Falha ao extrair spin_state (melhor esforço): %s", _e)

    behavioral_signals = None
    try:
        from agent.behavioral_signal_extractor import extrair_sinais_comportamentais_async
        behavioral_signals = await extrair_sinais_comportamentais_async(
            transcricao_parcial, historico, usuario_id=usuario_id, meeting_id=meeting_id,
        )
    except Exception as _e:
        logger.debug("[ShadowMode] Falha ao extrair behavioral_signals (melhor esforço): %s", _e)

    buyer_motivation = None
    try:
        from agent.buyer_motivation_extractor import extrair_buyer_motivation_async
        buyer_motivation = await extrair_buyer_motivation_async(
            transcricao_parcial, historico, usuario_id=usuario_id, meeting_id=meeting_id,
        )
    except Exception as _e:
        logger.debug("[ShadowMode] Falha ao extrair buyer_motivation (melhor esforço): %s", _e)

    entrada = {
        "meeting_memory": {
            "transcricao_parcial": transcricao_parcial,
            "historico": historico,
            "resumo_vivo": resumo_vivo,
            "diagnostico_atual": diagnostico_atual,
            "mapa_financeiro": mapa_financeiro,
            "historico_scores": historico_scores,
            "eventos": eventos,
        },
        "rag_context": client_context or None,
        "objections": objections,
        "historical_patterns": historical_patterns,
        "opportunity_memory": opportunity_memory,
        "opportunity_graph": opportunity_graph,
        "spin_state": spin_state,
        "behavioral_signals": behavioral_signals,
        "buyer_motivation": buyer_motivation,
    }

    inicio = _time.monotonic()
    recomendacao_nova = None
    erro = None
    try:
        recomendacao_nova = await raciocinar_async(entrada, usuario_id=usuario_id, meeting_id=meeting_id)
    except Exception as e:
        erro = f"{type(e).__name__}: {e}"
        # Diagnóstico temporário (V.1.4.136) — ver nota em
        # agent/sales_reasoning_engine.py::_registrar_audit_trail.
        logger.warning("[ShadowMode] raciocinar_async falhou (esperado, melhor esforço): %s", erro)
    latency_ms = int((_time.monotonic() - inicio) * 1000)

    cost_usd = None
    try:
        from api import ai_features
        from api.database import obter_ultimo_ai_usage_event
        evento = obter_ultimo_ai_usage_event(ai_features.SALES_REASONING_RACIOCINIO, meeting_id)
        if evento:
            cost_usd = evento.get("cost_usd")
    except Exception:
        pass

    registro = montar_registro_shadow(recomendacao_atual, recomendacao_nova, latency_ms, cost_usd, erro)
    try:
        from api.database import criar_shadow_mode_comparison
        criar_shadow_mode_comparison(meeting_id=meeting_id, usuario_id=usuario_id, origem="shadow", **registro)
    except Exception as _e:
        logger.debug("[ShadowMode] Falha ao persistir comparação (melhor esforço): %s", _e)

_FALLBACK_NBA = {
    "type": "question",
    "category": "descoberta_dor",
    "title": "Descoberta Inicial",
    "message": "Me conta um pouco mais sobre o que motivou voces a buscar uma solucao agora?",
    "objective": "Entender motivacao",
    "reason": "Contexto insuficiente para sugerir acao estrategica.",
    "expected_effect": "Abrir espaco para identificar a dor real",
    "risk_if_ignored": "A conversa pode nao avancar sem contexto do cliente.",
    "follow_up": None,
    "confidence": 0.5,
}

_FALLBACK_MATURITY = {
    "total": 0,
    "dor_identificada": 0,
    "impacto_quantificado": 0,
    "urgencia_identificada": 0,
    "budget_identificado": 0,
    "decisores_mapeados": 0,
    "valor_verbalizado_cliente": 0,
    "proximo_passo_claro": 0,
}


def _nba_para_nbq(nba: dict) -> dict:
    fbq = _FALLBACK_NBA["message"]
    return {
        "question": nba.get("message") or fbq,
        "category": nba.get("category") or "descoberta_dor",
        "objective": nba.get("objective") or "",
        "reason": nba.get("reason") or "",
        "expected_score_impact": "+10",
        "urgency_level": "high" if (nba.get("confidence") or 0) >= 0.8 else "medium",
        "follow_up_question": nba.get("follow_up"),
    }


def _safe(result, default=None):
    """Retorna result se for dict, caso contrário default."""
    if isinstance(result, Exception):
        return default if default is not None else {}
    if not isinstance(result, dict):
        return default if default is not None else {}
    return result


def _mesclar(coach: dict, disc: dict, finance: dict, closer: dict, bigfive: dict) -> dict:
    resultado: dict = {"status": "updated"}

    # T5.1 — Coach
    resultado["conversation_stage"] = coach.get("conversation_stage") or "abertura"
    resultado["next_best_action"]   = coach.get("next_best_action") or dict(_FALLBACK_NBA)
    resultado["alerta_urgente"]     = coach.get("alerta_urgente")
    resultado["dica_vendedor"]      = coach.get("dica_vendedor")
    resultado["filtro_cliente"]     = coach.get("filtro_cliente") or {}
    resultado["recapitulacao"]      = coach.get("recapitulacao")
    resultado["dado_esquecido"]     = coach.get("dado_esquecido")
    resultado["texto_falavel"]      = coach.get("texto_falavel") or coach.get("proxima_fala")
    resultado["proxima_fala"]       = resultado["texto_falavel"]
    resultado["key_moments"]        = coach.get("key_moments") or []
    resultado["eventos"]            = coach.get("eventos") or []
    resultado["events"]             = list(resultado["eventos"])

    # T5.2 — DISC
    resultado["perfil_disc"] = disc.get("perfil_disc") or {}
    resultado["kare_type"]   = disc.get("kare_type") or "attain"
    resultado["temperatura"] = disc.get("temperatura") or {}

    # T5.3 — Finance
    resultado["mapa_financeiro"]   = finance.get("mapa_financeiro") or {}
    resultado["objecao_detectada"] = finance.get("objecao_detectada") or {}

    # Big Five — inferencia comportamental de personalidade (nunca recebe
    # astrologia como entrada; astrologia so entra no relatorio final,
    # nunca aqui, garantindo por construcao que uma nao contamina a outra)
    resultado["perfil_bigfive"] = bigfive.get("perfil_bigfive") or {}

    # T5.4 — Closer
    resultado["score_compra"]    = closer.get("score_compra") or {"valor": None, "justificativa": None}
    resultado["maturity_score"]  = closer.get("maturity_score") or dict(_FALLBACK_MATURITY)
    resultado["resumo_vivo"]     = closer.get("resumo_vivo") or ""
    resultado["current_diagnosis"] = closer.get("current_diagnosis") or {}
    resultado["proxima_acao"]    = closer.get("proxima_acao") or closer.get("acao_recomendada")
    resultado["acao_recomendada"] = resultado["proxima_acao"]
    resultado["proxima_pergunta"] = closer.get("proxima_pergunta")

    # Propensão de Compra — rótulo determinístico derivado do score interno
    # (Alta/Média/Baixa/Não determinada), sem nenhuma chamada de IA extra.
    # score_compra continua calculado e persistido normalmente; só deixa de
    # ser exibido como número na extensão.
    resultado["propensao"] = {"nivel": classificar_propensao(resultado["score_compra"].get("valor"))}

    # Cross-links para backward compat
    resultado["next_best_question"] = _nba_para_nbq(resultado["next_best_action"])
    if resultado["resumo_vivo"] and not resultado.get("recapitulacao"):
        resultado["recapitulacao"] = resultado["resumo_vivo"]
    resultado["historico_resumido"] = resultado.get("resumo_vivo") or ""

    # Garante maturity_score.total
    ms = resultado["maturity_score"]
    if not ms.get("total"):
        ms["total"] = sum(v for k, v in ms.items() if k != "total" and isinstance(v, (int, float)))

    return resultado


async def analisar_fragmento_multi(
    transcricao_parcial: str,
    historico: str = "Inicio da conversa",
    perfil_disc_atual: str = "Ainda nao identificado",
    mapa_financeiro: dict = None,
    resumo_vivo: str = "Resumo ainda nao disponivel",
    diagnostico_atual: dict = None,
    historico_scores: list = None,
    eventos: list = None,
    skill_context: str = "",
    client_context: str = "",
    usuario_id: str | None = None,
    meeting_id: str | None = None,
    perfil_bigfive_atual: dict = None,
    transcricao_nova: str = "",
) -> dict:
    diag = diagnostico_atual or {}
    scores = historico_scores or []
    evts = eventos or []
    mapa = mapa_financeiro or {}
    rv = resumo_vivo or "Resumo ainda nao disponivel"

    try:
        from services.observability.factory import get_observability_provider
        obs = get_observability_provider()
    except Exception:
        from services.observability.noop_provider import NoOpObservabilityProvider
        obs = NoOpObservabilityProvider()
    retrieval_span = None
    try:
        retrieval_span = obs.start_span(name="retrieval", meeting_id=meeting_id)
    except Exception:
        retrieval_span = None

    # RAG context — busca uma vez e compartilha entre agentes via client_context
    try:
        query_rag = f"{transcricao_parcial} {historico}"
        rag = await buscar_contexto_similar(query_rag, top_k=3)
        if rag:
            client_context = (client_context or "") + f"\n\n{rag}"
        try:
            obs.record_retrieval(source="base_conhecimento", query=query_rag,
                                  result_count=1 if rag else 0, meeting_id=meeting_id)
        except Exception:
            pass
    except Exception as _e:
        logger.debug("[Multiagente] RAG falhou: %s", _e)

    # Sales Memory — memórias comerciais extraídas de reuniões anteriores
    try:
        from agent.sales_memory import buscar_contexto_para_reuniao
        query_mem = f"{transcricao_parcial} {historico}"
        mem_ctx = buscar_contexto_para_reuniao(query_mem, top_k=3)
        if mem_ctx:
            client_context = (client_context or "") + f"\n\n{mem_ctx}"
        try:
            obs.record_retrieval(source="sales_memory", query=query_mem,
                                  result_count=1 if mem_ctx else 0, meeting_id=meeting_id)
        except Exception:
            pass
    except Exception as _e:
        logger.debug("[Multiagente] Sales Memory falhou: %s", _e)

    # Knowledge Compiler (Fase 3) — KnowledgeItems aprovados (livros/playbooks compilados)
    try:
        from api.database import buscar_conhecimento_compilado_similar
        query_kc = f"{transcricao_parcial} {historico}"
        kc_ctx = buscar_conhecimento_compilado_similar(query_kc, top_k=2)
        if kc_ctx:
            client_context = (client_context or "") + f"\n\n{kc_ctx}"
        try:
            obs.record_retrieval(source="knowledge_compiler", query=query_kc,
                                  result_count=1 if kc_ctx else 0, meeting_id=meeting_id)
        except Exception:
            pass
    except Exception as _e:
        logger.debug("[Multiagente] Knowledge Compiler RAG falhou: %s", _e)

    try:
        if retrieval_span is not None:
            obs.end_span(retrieval_span)
    except Exception:
        pass

    coach_coro   = analisar_coach(transcricao_parcial, historico, rv, diag, evts, skill_context, client_context, usuario_id, meeting_id)
    disc_coro    = analisar_disc(transcricao_parcial, historico, perfil_disc_atual, diag, usuario_id, meeting_id)
    finance_coro = analisar_finance(transcricao_parcial, historico, mapa, usuario_id, meeting_id)
    closer_coro  = analisar_closer(transcricao_parcial, rv, scores, diag, usuario_id, meeting_id)
    bigfive_ativo = bigfive_agent_ativo()
    bigfive_coro = (
        analisar_bigfive(transcricao_parcial, historico, perfil_bigfive_atual or {}, diag, usuario_id, meeting_id)
        if bigfive_ativo else None
    )

    async def _com_span(nome: str, coro):
        # Span iniciado DENTRO da coroutine — asyncio.gather cria uma Task
        # por coroutine (cada uma com copia propria do contextvars.Context),
        # entao isso isola o span por agente sem vazar entre Coach/DISC/
        # Finance/Closer. Nao mover start_span pra antes do gather.
        span = None
        try:
            span = obs.start_span(name=f"agent.{nome}", meeting_id=meeting_id)
        except Exception:
            span = None
        try:
            return await coro
        finally:
            if span is not None:
                try:
                    obs.end_span(span)
                except Exception:
                    pass

    coroutines = [
        _com_span("coach", coach_coro),
        _com_span("disc", disc_coro),
        _com_span("finance", finance_coro),
        _com_span("closer", closer_coro),
    ]
    if bigfive_coro is not None:
        coroutines.append(_com_span("bigfive", bigfive_coro))

    resultados = await asyncio.gather(*coroutines, return_exceptions=True)

    coach_r, disc_r, finance_r, closer_r = resultados[:4]
    bigfive_r = resultados[4] if bigfive_coro is not None else {}

    nomes_resultados = [("Coach", coach_r), ("DISC", disc_r), ("Finance", finance_r), ("Closer", closer_r)]
    if bigfive_coro is not None:
        nomes_resultados.append(("BigFive", bigfive_r))
    for nome, res in nomes_resultados:
        if isinstance(res, Exception):
            logger.warning("[Multiagente] %s falhou: %s", nome, res)

    # Cost Intelligence Fase 1 — soma o custo dos agentes ANTES do merge:
    # _mesclar() nao preserva os campos _*_ia dos agentes (monta o dict final
    # campo a campo), entao sem isso MeetingMemory.provider_cost_estimate
    # ficava sempre 0.0 para todo o trafego de tempo real (achado da auditoria
    # em docs/cost-intelligence-audit.md). bigfive_r fica {} (custo 0) quando
    # o kill-switch BIGFIVE_AGENT_ENABLED esta desligado.
    custo_ciclo = sum(
        (_safe(r).get("_custo_estimado_ia") or _safe(r).get("_custo_real_usd") or 0.0)
        for r in (coach_r, disc_r, finance_r, closer_r, bigfive_r)
    )

    resultado = _mesclar(
        _safe(coach_r),
        _safe(disc_r),
        _safe(finance_r),
        _safe(closer_r),
        _safe(bigfive_r),
    )
    resultado["_custo_ciclo_ia_usd"] = round(custo_ciclo, 6)

    # Fase 24 ("PROMPT MESTRE — SALE-IA V2") — Piloto: se este
    # usuario_id está dentro do rollout, o modelo novo passa a
    # influenciar de verdade `resultado` (await real, soma latência) —
    # mutuamente exclusivo com o Shadow Mode abaixo (nunca chama
    # raciocinar_async() 2x no mesmo ciclo pro mesmo vendedor).
    usar_piloto = False
    try:
        from agent.pilot_rollout_rules import deve_usar_modelo_novo
        usar_piloto = deve_usar_modelo_novo(usuario_id, pilot_mode_atual(), pilot_usuarios())
    except Exception as _e:
        logger.debug("[Piloto] Falha ao avaliar rollout (fail-safe, modelo atual mantido): %s", _e)

    if usar_piloto:
        try:
            await _aplicar_piloto_sales_reasoning(
                resultado, transcricao_parcial, historico, rv, diag, mapa,
                scores, evts, client_context, usuario_id, meeting_id,
            )
        except Exception as _e:
            logger.warning("[Piloto] Falha inesperada, modelo atual preservado: %s", _e)
    else:
        # Fase 23 — Teste em Shadow Mode: fire-and-forget, nunca
        # aguardado, nunca pode atrasar o retorno abaixo nem mudar
        # `resultado`. Kill-switch SHADOW_MODE_ENABLED (default false)
        # — ver shadow_mode_ativo().
        try:
            _agendar_shadow_mode(
                resultado, transcricao_parcial, historico, rv, diag, mapa,
                scores, evts, client_context, usuario_id, meeting_id,
            )
        except Exception as _e:
            logger.debug("[ShadowMode] Falha ao agendar (melhor esforço): %s", _e)

    # Fase 10 (Tarefas 10.1+10.2) — roda depois do Piloto/Shadow Mode
    # acima, pra rastrear a recomendação que o vendedor de fato vê
    # (resultado["next_best_action"] já reflete a substituição do
    # Piloto quando aplicável).
    try:
        await _rastrear_recomendacao(resultado, transcricao_nova, meeting_id)
    except Exception as _e:
        logger.debug("[RecommendationTracking] Falha inesperada (melhor esforço): %s", _e)

    return resultado
