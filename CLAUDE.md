# SALEIA — Instruções para Claude Code

## Leia sempre ao iniciar uma conversa

1. **[CHANGELOG.md](CHANGELOG.md)** — Registro completo de tudo implementado
2. **[docs/CURRENT_STATE.md](docs/CURRENT_STATE.md)** — Estado atual, infraestrutura, pendências

## Contexto do projeto

**SALEIA** é um assistente de vendas com IA para Google Meet.
- Backend: FastAPI + Python 3.14, porta 8000
- Frontend: HTML/JS vanilla (login.html, dashboard.html, cenario.html, manual.html, visual-scenario.html)
- Banco: MySQL local na VPS (`127.0.0.1`, ~2ms)
- VPS: `37.27.214.33` (Hetzner CPX32, Helsinki) — serviço `saleia.service` (systemd)
- Domínio: `api.saleia.app.br`
- Repo: `https://github.com/fasterdrible-lab/SALE-IA.git` branch `main`
- Versão atual: **V.1.4.54** (backend) · extensão Chrome **V.1.4.5** (`chrome-extension/manifest.json`, versionada separadamente)
- Usuário admin: `phpos35@gmail.com`

## Deploy

```bash
cd /opt/saleia && git pull origin main && systemctl restart saleia
```

Não sobrescrever em deploy: `.env`, `venv/`, `data/`, `logs/`

## Regras importantes

- Nunca commitar `.env`, `data/saleia.db`, `data/metricas.db` ou PDFs com nomes de clientes
- Nunca expor chaves de API no frontend
- Frontend usa `fetchJsonWithFallback(path, init)` que retorna um `Response` — sempre chamar `.json()` depois
- Extensão Chrome: após qualquer mudança em `chrome-extension/`, precisa ser reinstalada manualmente no browser
- Extensão Chrome (desde V.1.4.40): sidebar/popup só mostram o que ajuda o vendedor durante a reunião — nada de URL do backend, nome/modelo de provedor de IA ou score numérico; isso fica só no Dashboard

## Stack técnica

| Camada | Tecnologia |
|---|---|
| API | FastAPI + Uvicorn (Python 3.14) |
| Auth | JWT (PyJWT) + bcrypt |
| IA | DeepSeek → OpenAI → Anthropic → Gemini (fallback chain) |
| RAG | NumPy cosine similarity + provedor pluggable (`services/embeddings/` — Ollama/`embeddinggemma` local por padrão, OpenAI `text-embedding-3-small` opcional) |
| Banco | MySQL local (PyMySQL) |
| Frontend | HTML/CSS/JS vanilla, sem framework |
| Deploy | Hetzner VPS + Nginx + Certbot SSL + Cloudflare |
| Observabilidade | SQLite rolling 24h + OpenTelemetry → Grafana Cloud Tempo |

## Arquitetura do Motor de Análise (V.1.4.28, propensão desde V.1.4.40)

O endpoint `POST /tempo-real` retorna:
- `next_best_action` — ação consultiva recomendada (tipo: question/insight/warning/next_step)
- `conversation_stage` — estágio SPIN atual (abertura → compromisso)
- `kare_type` — classificação da conta (keep/attain/recapture/expand)
- `maturity_score` — maturidade da oportunidade (0-100, 7 critérios)
- `score_compra` — score de compra interno (0-100) — usado para diagnóstico e persistido, mas **não é mais exibido na extensão** (ver `propensao`)
- `propensao` — `{nivel}` alta/media/baixa/nao_determinada, derivado deterministicamente de `score_compra.valor` via `agent/propensao_rules.py` (sem chamada de IA extra); é o campo que a sidebar da extensão exibe
- `next_best_question` — alias de backward compat para extensões antigas

O detalhamento da propensão (fatores, evidências, o que falta para avançar) é gerado uma única vez por `PROMPT_RECAPITULACAO` (`api/main.py`) ao final da reunião — não em tempo real — e consumido pelo Dashboard.

## Piloto Claude Account Mode (V.1.4.44+)

Cada vendedor conecta a própria assinatura Claude via `claude setup-token` (dashboard → Configurações → card "Claude (piloto)"). Ponto único de execução: `agent/claude_account.py::ClaudeAccountExecutor`.

- **Isolamento de credencial**: o `claude_agent_sdk` monta o ambiente do subprocesso CLI herdando *todo* o `os.environ` do `saleia.service` — sem limpar `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` explicitamente em `options.env`, o piloto cobraria da conta central (Claude Code prioriza essas variáveis sobre `CLAUDE_CODE_OAUTH_TOKEN`).
- **Sem ferramentas de verdade**: usar `tools=[]`, não `allowed_tools=[]` — este último só remove pré-aprovação, não torna as ferramentas indisponíveis (doc do SDK). Só `allowed_tools=[]` faz o modelo tentar usar o conjunto padrão, cair em permissão negada e esgotar `max_turns`.
- **Sem expiração programada por tempo**: `agent/claude_account.py::_levantar_erro_classificado` distingue por conteúdo da mensagem de erro, não por timer — `RateLimitEvent`/padrão de limite → `USAGE_LIMIT_REACHED` (conexão continua `ativo`, só a janela de uso da assinatura esgotou, como em qualquer outro projeto Claude Code); padrão de auth (`401`/`expired`/`invalid token`/etc.) → `AUTH_REQUIRED` (marca `expirado`, exige reconectar).
- **Token colado deve ser sanitizado de whitespace em qualquer posição** (`re.sub(r"\s+", "", ...)`, não só `.strip()`) — copiar um token longo de um terminal com quebra de linha pode inserir um espaço no meio, que corrompe o token silenciosamente (conecta com 200 OK, só a análise revela o problema).
- Todos os 26 testes de `tests/test_claude_account.py` mockam `_executar_query`/`claude_agent_sdk.query` — nenhum exercita a configuração real do `ClaudeAgentOptions` contra o SDK/CLI de verdade. Os 3 bugs acima só apareceram no primeiro uso real de produção (22/08/2026).

### Fallback no tempo real (V.1.4.49)

A extensão Chrome pode opcionalmente logar (`/auth/login`, mesmo endpoint do Dashboard) — login é sempre opcional, quem não loga continua 100% anônimo como antes. Quando logado, `POST /tempo-real` resolve `usuario_id` via JWT e o repassa por toda a cadeia (`processador_tempo_real.py` → `orquestrador.py` → os 4 agentes). Se os 4 provedores centrais se esgotarem (`HTTPException(503)` de `api/ai_router.py`), `agent/multiagente/claude_fallback.py::chamar_ia_com_fallback_claude` tenta a conta Claude pessoal do usuário antes de desistir — só como fallback, nunca substitui os 4 centrais no caminho normal (evita drenar a janela de uso de 5h da assinatura a cada ciclo de 60s). Se o fallback também falhar, relança a exceção original, preservando a degradação graciosa já existente (`orquestrador.py::_safe()`).

**Limitação conhecida (achado em incidente real, 31/08/2026)**: o servidor não consegue distinguir "vendedor com extensão desatualizada" de "vendedor com extensão atualizada mas sem login" — a única pista era a ausência do header `Authorization`, que ocorre nos dois casos. Ver `X-Extensao-Versao` (V.1.4.50) abaixo.

### Versão da extensão nos logs (V.1.4.50)

Toda chamada da extensão ao backend (`fetchBackend`, `/audio-transcricao`, heartbeat de `/health`) envia `X-Extensao-Versao: <manifest.version>`. `api/main.py::_CorrelationMiddleware` lê esse header em qualquer rota (não só `/tempo-real`) e expõe via `_ext_ver_var` (`ContextVar`, mesmo padrão do `cid` de correlação) — todo log JSON estruturado (`_JsonFormatter`) ganha o campo `ext_ver`. Durante um incidente, `journalctl -u saleia | grep ext_ver` mostra imediatamente se a extensão do vendedor está desatualizada, sem precisar perguntar a ele.

## Cost Intelligence (Fase 1, V.1.4.51)

Fundação de custo real de IA — primeira fase de um roadmap maior (ver `docs/cost-intelligence-audit.md`). Ainda **não** tem dashboard, budget guard ou cost router; só captura e persiste dados corretos.

- **`api/pricing_catalog.py::obter_preco(provider, model)`** — preço por *modelo* (não mais por provedor genérico), com fallback e override por env (`PRICE_<PROVIDER>_<MODELO>_<CAMPO>_PER_MILLION`).
- **`api/cost_engine.py::calcular_custo(...)`** — cálculo puro; `estimar_usage(...)` é o fallback char/4 usado só quando o provedor não devolve tokens reais.
- **`api/ai_router.py::chamar_ia`/`chamar_ia_async`** ganharam `feature`/`meeting_id`/`usuario_id` keyword-only (default preserva os chamadores antigos) e agora leem o `usage` real de cada SDK (antes descartado) — `_usage_source_ia` no resultado diz `"provider"` ou `"estimated"`.
- **`api/database.py::AiUsageEvent`** (tabela `ai_usage_events`) — um registro por chamada de IA. Gravação é sempre melhor esforço (`registrar_evento_uso_ia`): nunca derruba o fluxo de vendas.
- **`api/ai_features.py`** — constantes de `feature` (ex.: `REALTIME_COACH`, `PLAYBOOK_GERACAO`) usadas em toda chamada de IA para saber depois onde o dinheiro foi gasto.
- **Bug fechado**: `agent/multiagente/orquestrador.py::_mesclar()` não preserva os campos `_*_ia` dos 4 agentes — por isso `analisar_fragmento_multi` agora soma o custo dos agentes em `resultado["_custo_ciclo_ia_usd"]` **antes** do merge. Sem isso, `MeetingMemory.provider_cost_estimate` (e `GET /historico/uso`) ficavam sempre em `R$0` para tempo real — o maior volume de chamadas do sistema.
- **Limitação conhecida**: nomes de campo de cache do DeepSeek/Gemini não foram validados contra uma resposta real (degradam com segurança para `0`); Claude Account fallback não expõe contagem de tokens, só custo agregado.

## Biblioteca de Inteligência / Knowledge Compiler (Fase 1, V.1.4.52)

Feature grande (roadmap de 6 fases) que transforma documentos comerciais (livros, playbooks, treinamentos, manuais) em conhecimento estruturado reutilizável pelo RAG/Sales Memory/Playbook/Skill. **Esta fase só cobre upload + extração determinística de texto — sem IA ainda.** Atrás de `KNOWLEDGE_COMPILER_ENABLED` (`false` por padrão, endpoints somem via `404`, mesmo padrão do `CLAUDE_ACCOUNT_PILOT`).

- **`services/knowledge_compiler/`**: `get_extractor(mime_type, filename)` despacha para o extractor certo (PDF via pypdf com fallback pdfplumber, DOCX via python-docx, TXT/MD, HTML via BeautifulSoup4). Chunking é por seção real (heading, ou tamanho de fonte detectado no PDF), nunca por corte fixo de caracteres — o LLM nunca abre o arquivo bruto diretamente, sempre recebe texto já extraído deterministicamente.
- **`sanitizer.py::sanitize_document_text()`**: o texto de um documento é dado, nunca instrução — remove só ruído técnico inequívoco (unicode de controle/formatação invisível) e **sinaliza sem remover** trechos que parecem prompt injection (`potential_instruction_injection`). Fases futuras devem bloquear texto sinalizado de virar `system_injection` de uma Skill sem revisão humana.
- **`api/database.py::KnowledgeSource`**: tabela SQLModel (`knowledge_sources`), sem `organization_id` — decisão deliberada (mesma linha da V.1.4.40: SALEIA é uso interno de uma única empresa, multi-tenancy não se aplica hoje).
- **Deduplicação por hash**: `POST /biblioteca/fontes` calcula `content_hash` (sha256) do arquivo — reenviar o mesmo arquivo reaproveita o registro existente em vez de reprocessar.
- **Extração é um passo manual separado** (`POST /biblioteca/fontes/{id}/extrair`), nunca automática no upload — controle de custo/processamento deliberado desde a Fase 1, mesmo sem custo de IA ainda (vale para quando a Fase 2 adicionar compilação com IA).
- **Fase 2 (V.1.4.53) — compilação com IA**: `services/knowledge_compiler/compiler.py::compilar_fonte()` — 1 chamada de IA por seção (não por tipo), extrai `KnowledgeItem`s de 7 tipos (`FRAMEWORK`, `OBJECTION`, `DISCOVERY_QUESTION`, `SCRIPT`, `ANTI_PATTERN`, `DECISION_RULE`, `CASE`). Seções sinalizadas `potential_instruction_injection` (Fase 1) são puladas, não só marcadas. `api/database.py::KnowledgeItem` é **SQLModel** (não raw-pymysql como `sales_memories`/`skills`) — decisão deliberada pra manter testável, já que os módulos raw-pymysql equivalentes não têm nenhum teste hoje. Dedup por embedding (`buscar_knowledge_item_similar`, threshold 0.92) nunca bloqueia nem faz merge automático, só marca `possivel_duplicado_de` — revisão humana decide. Todo item nasce `DRAFT`; só `APPROVED` deve entrar em qualquer fase futura de RAG. Estimativa de custo pré-voo (`estimar_custo_compilacao`, sem IA) reaproveita `api/cost_engine.py`/`api/pricing_catalog.py`, mostrada ao usuário antes de qualquer gasto real.
- **Fase 3 (V.1.4.54) — integração RAG/Skill/Playbook**: `api/database.py::buscar_conhecimento_compilado_similar()` — 3º bloco de RAG em `agent/multiagente/orquestrador.py::analisar_fragmento_multi` (junto de base_conhecimento e Sales Memory), busca só `KnowledgeItem`s `APPROVED`, `top_k=2`. Skill (`agent/skill_resolver.py::gerar_skill_de_knowledge_item`) e Playbook (`agent/playbook_generator.py::gerar_playbook_de_fonte`) são **manuais**, disparados pelo usuário por item/fonte — nunca automáticos, e sem custo de IA (reshape de dados já estruturados). Skill nova entra com triggers amplos (qualquer DISC/estágio/score) e prioridade 60 — `resolver_melhor_skill()` só elege 1 vencedora por prioridade (não é RAG), então competir sem revisão humana antes seria arriscado. **Decisão deliberada**: `KnowledgeItem` NÃO é mapeado para `sales_memory` — duplicaria conteúdo no contexto da IA já que a busca direta em `knowledge_items` cobre isso.
- **Roadmap não iniciado**: Fase 4 (progressive disclosure / context builder com ranking além de cosseno puro), Fase 5 (governança/versionamento/segurança avançada), Fase 6 (UI final + métricas de uso + feedback). Detalhe completo no CHANGELOG (V.1.4.52-1.4.54).
