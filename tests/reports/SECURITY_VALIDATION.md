# SALEIA — Auditoria Estática de Segurança

Data: 2026-09-08
Escopo: leitura de código apenas (sem execução), backend FastAPI (`api/`, `agent/`, `services/`), frontend vanilla (`frontend/`), extensão Chrome (`chrome-extension/`).
Metodologia: tentativa deliberada de provar falhas (não confirmar segurança). Single-tenant é decisão de produto deliberada (ver CLAUDE.md) — isolamento multi-tenant não foi testado/cobrado.

Resumo de contagem por severidade: **CRITICAL: 1 (corrigido) · HIGH: 6 (todas as 6 corrigidas) · MEDIUM: 3
(todas as 3 corrigidas/ampliadas) · LOW: 2 (as 2 corrigidas — L2 validado empiricamente em Chrome real via
Playwright)** (12 achados no total, além de 9 controles confirmados como corretamente protegidos, listados
ao final).

**Correções aplicadas em 08/09/2026** (código + testes de regressão passando, suíte completa sem falha
nova): C1 (JWT_SECRET, também mitigado em produção), H1 (CORS restrito às origens reais), H2 (auth em 12
endpoints dashboard-only), H3 (assinatura do webhook Tactiq conectada), H4 (max_length + rate limit em
`/audio-transcricao`, sem exigir login), H5 (redação de chave Gemini/`?key=`), H6 (rate limit em
`/auth/login`), M1 (escape de aspas simples + validação de `meeting_id`), M2 (regex de prompt injection
ampliado de 6 para 19 padrões), M3 (validação de magic bytes em PDF/DOCX), L1 (4 endpoints com crash
confirmado corrigidos), L2 (permissão `tabs` removida — validado empiricamente em Chrome real via
Playwright, ver seção própria). Mais 2 achados fora do relatório original, encontrados durante a correção:
bug determinístico de `classificar_propensao(NaN)` (ver FUNCTIONAL_VALIDATION.md) e 2 testes em
`test_realtime_memory.py` que mockavam o módulo errado (`agent.agente_tempo_real`, código morto) e faziam
uma chamada de IA real não intencional a cada execução da suíte — corrigido para mockar
`agent.multiagente.orquestrador.analisar_fragmento_multi`, o caminho real.

---

## CRITICAL

### C1 — `JWT_SECRET` tem fallback hardcoded público no código-fonte

- **Status**: **CORRIGIDO EM PRODUÇÃO em 08/09/2026** — confirmado via SSH que a VPS não definia `JWT_SECRET`
  (`grep -c` retornou 0), ou seja, esta vulnerabilidade estava **ativa e explorável** até a correção. Gerado
  um segredo forte (`secrets.token_urlsafe(48)`), gravado em `/opt/saleia/.env` (backup do `.env` anterior
  preservado na própria VPS antes da escrita) e `systemctl restart saleia` — serviço voltou `active`,
  `GET /health` local respondeu 200. **Efeito colateral esperado**: todos os JWTs emitidos antes da troca
  foram invalidados (usuários logados precisam logar novamente). **Ainda pendente**: remover o fallback
  hardcoded do código-fonte (`api/main.py:2654`) e adicionar trava de startup (mesmo padrão de
  `CLAUDE_TOKEN_ENC_KEY`) — a correção aplicada hoje resolve o sintoma em produção, não a causa raiz no
  código; um redeploy futuro sem essa variável reintroduz a falha.
- **Severidade original**: CRITICAL (antes da correção em produção)
- **Severidade**: CRITICAL
- **Evidência**: `api/main.py:2654`
  ```python
  _JWT_SECRET = os.environ.get("JWT_SECRET", "saleia-secret-change-me")
  ```
  O `.env` local do repositório (não versionado, mas presente em disco) **não define `JWT_SECRET`** (confirmado: `grep -c "^JWT_SECRET=" .env` → `0`). Não há nenhuma verificação de startup que aborte a aplicação se a variável estiver ausente — ela simplesmente cai no valor padrão, que é público (está no histórico do GitHub).
  Contraste direto no mesmo arquivo: `agent/claude_account.py:120-127` faz o certo para outro segredo —
  ```python
  def _chave_fernet() -> Fernet:
      chave = os.getenv("CLAUDE_TOKEN_ENC_KEY")
      if not chave:
          raise RuntimeError("CLAUDE_TOKEN_ENC_KEY não configurada no .env — necessária ...")
  ```
- **Impacto**: Se o `.env` da VPS de produção também não define `JWT_SECRET` (não verificável a partir do repo, mas o próprio `.env` de referência do projeto não o define, o que é evidência de que é fácil esquecer), qualquer pessoa pode forjar um JWT válido — inclusive com `"perfil": "admin"` — usando o segredo padrão público, contornando completamente `_req_auth`/`_req_admin`/`_req_claude_pilot`/`_req_biblioteca` (todos usam o mesmo `_JWT_SECRET`). Isso é bypass total de autenticação/autorização do sistema.
- **Correção recomendada**: Remover o fallback; abortar o startup (`raise RuntimeError`) se `JWT_SECRET` não estiver definido, no mesmo padrão já usado para `CLAUDE_TOKEN_ENC_KEY`. Confirmar imediatamente que a VPS de produção tem a variável configurada com um valor forte e único.

---

## HIGH

### H1 — CORS libera qualquer origem com credenciais habilitadas

- **Status**: **CORRIGIDO em 08/09/2026**. `allow_origins` restrito a `https://api.saleia.app.br`/
  `http://api.saleia.app.br` + `allow_origin_regex` cobrindo `localhost`/`127.0.0.1` (qualquer porta, dev
  local) e túneis `*.ngrok-free.{app,dev}` — mesma lista de `host_permissions` já declarada em
  `chrome-extension/manifest.json`. **Achado que destrava a correção com segurança**: confirmado por grep
  que a extensão Chrome (`content.js`/`background.js`/`popup.js`) nunca chama `fetch()` diretamente — tudo
  passa por `chrome.runtime.sendMessage` → `background.js`, que é isento de CORS por ter `host_permissions`
  (CORS só governa `fetch`/`XHR` feito por JS de página/contexto de aba, não o service worker da extensão).
  Ou seja, o wildcard nunca foi necessário para a extensão funcionar — o comentário original no código
  ("permite requisições da extensão Chrome") descrevia um mecanismo que não é como CORS/extensões realmente
  interagem. Verificado com `TestClient`: origem de produção/localhost/ngrok recebem
  `Access-Control-Allow-Origin` refletido; `https://evil.com` e um golpe de subdomínio
  (`https://api.saleia.app.br.evil.com`) recebem `None` (bloqueados).
- **Severidade original**: HIGH
- **Severidade**: HIGH
- **Evidência**: `api/main.py:118-123`
  ```python
  CORSMiddleware,
  allow_origins=["*"],
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
  ```
- **Impacto**: `allow_credentials=True` com `allow_origins=["*"]` faz o Starlette refletir dinamicamente o header `Origin` da requisição (em vez de enviar `*` literal, que o browser rejeitaria com credentials) — na prática, qualquer site da internet pode fazer requisições "credenciadas" (cookies, se existissem) contra a API a partir do browser da vítima. Como a autenticação aqui é via header `Authorization: Bearer` manual (não cookie automático), o roubo direto de token não ocorre só por causa do CORS — mas isso **amplia drasticamente** o impacto dos achados H2/H3 abaixo: qualquer página maliciosa pode, via JS, disparar chamadas `fetch` diretas contra todos os endpoints já sem autenticação (listar/apagar sessões, gerar relatórios pagos, etc.) a partir do navegador de qualquer visitante, sem precisar de XSS nem de token.
- **Correção recomendada**: Restringir `allow_origins` à(s) origem(ns) real(is) do frontend (`https://api.saleia.app.br`, e localhost em dev) em vez de `"*"`.

### H2 — Múltiplos endpoints de dados/sessão sem nenhuma autenticação

- **Status**: **CORRIGIDO em 08/09/2026** para os endpoints confirmados como dashboard-only (não usados
  anonimamente pela extensão Chrome — confirmado por grep em `chrome-extension/*.js`, que só chama
  `/iniciar-sessao`, `/recapitulacao-viva`, `/tempo-real`, `/audio-transcricao` e `/auth/login` sem
  garantia de token). Adicionado `_req_auth(authorization)` a: `GET/DELETE /sessoes/{id}`, `GET /sessoes`,
  `POST /sessoes/{id}/exportar-base`, `GET/POST/DELETE /base`, `GET /relatorios`, `POST
  /diagnostico-financeiro`, `/perfil-disc`, `/recapitulacao-completa`, `/recapitulacao-manual`, `POST
  /generate-visual-scenario`, `GET /visual-scenarios/{id}` — mesmo padrão já usado em `/clientes`/`/skills`.
  **Intencionalmente NÃO corrigidos** (quebrariam uso anônimo real e documentado da extensão/popup):
  `POST /iniciar-sessao` e `/recapitulacao-viva` (chamados por `content.js` sem garantia de header
  `Authorization` — `background.js` só anexa o Bearer se o vendedor optou por logar) e `GET /relatorio`
  (singular — aberto por `popup.js` via `chrome.tabs.create`, uma navegação de aba que não consegue anexar
  headers customizados). Esses 3 seguem abertos por design; ver recomendação abaixo.
- **Status original (antes da correção)**: Vulnerável
- **Severidade**: HIGH
- **Evidência**: varredura sistemática das 122 rotas de `api/main.py` confirmou que os seguintes endpoints não chamam `_req_auth`/`_req_admin`/`_req_biblioteca`/`_req_claude_pilot` em nenhum ponto do corpo da função:
  - `GET /sessoes`, `GET /sessoes/{id}`, **`DELETE /sessoes/{id}`** (`api/main.py:1807-1852`) — lista, lê e **apaga** qualquer sessão de reunião (transcrição + análise de IA) de qualquer vendedor.
  - `POST /iniciar-sessao`, `POST /sessoes/{id}/exportar-base` (`api/main.py:1855-1885`).
  - `GET /base`, `POST /base` (`api/main.py:1888-1997`) — lista e **adiciona** documentos à base de conhecimento compartilhada (o `POST` dispara uma chamada real ao provedor de embedding configurado).
  - `GET /relatorios`, `GET /relatorio` (`api/main.py:927-1000`, `1404-1463`) — lista/exibe os relatórios de reunião mais recentes de toda a empresa (probabilidade de fechamento, provedor de IA usado, dados completos em JSON).
  - `POST /diagnostico-financeiro`, `/perfil-disc`, `/recapitulacao-completa`, `/recapitulacao-viva`, `/recapitulacao-manual` (várias linhas entre 814-1759) — cada chamada dispara uma requisição real e paga a um provedor de IA.
  - `POST /generate-visual-scenario`, `GET /visual-scenarios/{meeting_id}` (`api/main.py:2594-2635`).

  Comparação relevante: `GET /base/{doc_id}/download` (`api/main.py:2000-2005`) **exige** `_req_auth` explicitamente, com comentário no código dizendo que a Base é compartilhada mas "a permissão é simplesmente 'estar logado'" — confirmando que a ausência de auth nos endpoints irmãos acima (listar/adicionar à mesma Base) é inconsistência, não decisão deliberada.
- **Impacto**: Qualquer pessoa com acesso à URL da API (não precisa estar logada) pode ler todo o histórico de reuniões/relatórios da empresa, apagar sessões de outros vendedores, injetar conteúdo na base de conhecimento compartilhada (que alimenta o RAG usado por todos os agentes de IA), e gerar custo real de IA sem limite via os endpoints de diagnóstico/recapitulação.
- **Correção recomendada**: Adicionar `_req_auth(authorization)` (ou `_req_admin` onde aplicável) em todos os endpoints listados, seguindo o mesmo padrão já usado em `/clientes`, `/skills`, `/base/{doc_id}/download`.

### H3 — `/webhook/tactiq` roda sem validação de assinatura; a implementação segura existe mas está órfã (nunca importada)

- **Status**: **CORRIGIDO em 08/09/2026** — `receber_webhook_tactiq` (`api/main.py`) agora lê o corpo bruto da
  requisição e chama `api.webhook_tactiq._validar_assinatura_webhook(body, header)` antes de processar
  qualquer coisa, devolvendo 401 se `TACTIQ_WEBHOOK_SECRET` estiver configurado e a assinatura não bater.
  **Decisão deliberada**: não substituí o pipeline de processamento inteiro pelo de `processar_webhook_tactiq`
  (que faz mais coisas — MeetingMemory, diagnóstico final, notificação ao vendedor) porque são duas
  implementações que divergem em comportamento além da assinatura, e trocar a ativa por engano poderia mudar
  silenciosamente o formato do relatório gerado em produção. Só portei a validação de assinatura, que é
  especificamente o que este achado cobra. **Comportamento preservado quando `TACTIQ_WEBHOOK_SECRET` não
  está configurado** (aceita sem validar, como antes) — evita quebrar quem ainda não configurou o segredo.
  **Ainda pendente**: confirmar se a VPS de produção já tem `TACTIQ_WEBHOOK_SECRET` definido (se não tiver,
  esta correção de código não muda o comportamento real até alguém configurar a variável); e considerar,
  como item separado de produto, se vale unificar as duas implementações do webhook.
- **Status original (antes da correção)**: Vulnerável
- **Severidade**: HIGH
- **Evidência**: A rota realmente ativa em `api/main.py:737-753` (`receber_webhook_tactiq`) não valida nada além de "transcript não vazio", e agenda `processar_transcricao_completa` em background — que dispara **3 chamadas reais de IA** (`chamar_gpt` para recapitulação, diagnóstico financeiro e perfil DISC).
  Existe, separadamente, `api/webhook_tactiq.py::_validar_assinatura_webhook` (linhas 67-95) com validação HMAC-SHA256 correta via `hmac.compare_digest` (comparação segura contra timing attack) usando `TACTIQ_WEBHOOK_SECRET`, além de `_validar_relatorio_id`/`salvar_relatorio` com proteção explícita contra path traversal (`caminho.is_relative_to(pasta_base)`).
  Confirmado por grep que `api/webhook_tactiq.py` **nunca é importado por `api/main.py`** (0 ocorrências de `webhook_tactiq` em `main.py` fora da própria função homônima não relacionada) — o único lugar que exercita esse módulo é `tests/test_final_diagnosis.py`, o que dá falsa confiança de que o webhook está protegido.
- **Impacto**: Qualquer pessoa pode forjar payloads de "Tactiq" e (a) gerar custo real de IA ilimitado (3 chamadas por request, sem rate limit), (b) poluir os relatórios armazenados com dados falsos/maliciosos.
- **Correção recomendada**: Substituir `receber_webhook_tactiq` em `api/main.py` para delegar a `api.webhook_tactiq.validar_e_processar_webhook(request)` (já pronta e testada), ou portar a validação de assinatura HMAC para a rota ativa.

### H4 — `POST /audio-transcricao` sem autenticação, sem limite de tamanho de payload e sem rate limiting

- **Status**: **CORRIGIDO PARCIALMENTE em 08/09/2026**. Auth continua deliberadamente ausente — a extensão
  chama este endpoint durante uma reunião mesmo sem vendedor logado (mesmo padrão anônimo de `/tempo-real`
  e `/iniciar-sessao`, confirmado no JS da extensão), exigir login quebraria isso. Em vez disso: (1)
  `audio_base64` ganhou `max_length=28_000_000` (Pydantic `Field`) — payload maior que ~20MB decodificados
  agora dá 422 em vez de aceitar sem limite; (2) rate limit por IP (`_rate_limit_por_ip`, mesmo padrão do
  bloqueio de `/auth/login`): 40 chamadas/60s — folga generosa (um chunk real a cada ~15s = 4/min por
  reunião) pra não travar uso legítimo de múltiplas reuniões simultâneas atrás do mesmo IP, mas barra flood.
  Verificado: 41ª chamada no mesmo IP em 60s recebe 429; payload de 30MB recebe 422.
  **Limitação conhecida, não resolvida**: `_client_ip` prioriza `X-Forwarded-For` sobre
  `request.client.host`, mas não foi possível confirmar se o Nginx real da VPS propaga esse header (config
  não está versionada no repo) — se não propagar, o limite de 40/60s vira efetivamente por-toda-a-VPS em vez
  de por-cliente, ainda proteção real contra flood total, só menos granular do que o ideal.
- **Severidade original**: HIGH
- **Severidade**: HIGH
- **Evidência**: `api/main.py:2532-2557`; `AudioTranscricaoRequest.audio_base64: str` (`api/main.py:359-362`) não tem `max_length`. Busca por bibliotecas de rate limiting (`slowapi`, `Limiter`, etc.) em todo `api/` retornou zero resultados — o único `HTTPException(429)` existente é `verificar_loop_caro` (`api/otimizacao.py:185-218`), que é um circuito de custo por reunião **desligado por padrão** (`OTIMIZACAO_LOOP_MAX_CUSTO_USD` "sem default" — CLAUDE.md), não um rate limiter genérico.
- **Impacto**: Endpoint dispara transcrição paga (OpenAI Whisper/Groq/Whisper local) por chamada, sem autenticação e sem limite de corpo — vetor direto de exaustão financeira (flood de chunks de áudio) e, sem limite superior de tamanho na aplicação, também de exaustão de memória caso o Nginx/uvicorn na frente não imponha um teto (não verificável a partir do repositório — nenhum arquivo de config Nginx está versionado).
- **Correção recomendada**: Exigir autenticação (ou, no mínimo, uma chave de dispositivo/extensão), adicionar `max_length` ao campo, e implementar rate limiting por IP/usuário nesse e nos demais endpoints públicos de alto custo.

### H5 — Redação de segredos em mensagens de erro de IA tem lacuna (formato de chave do Gemini) e o resultado é devolvido ao chamador anônimo

- **Status**: **CORRIGIDO em 08/09/2026** (a lacuna do regex). `_safe_error` (`api/ai_router.py`) ganhou 2
  padrões novos: `AIza[0-9A-Za-z_\-]{35}` (formato de chave Google/Gemini) e `[?&]key=\S+` (parâmetro de URL
  usado pelo SDK do Gemini). Verificado com casos sintéticos: uma URL com `?key=AIzaSy...` e uma mensagem de
  erro citando a chave diretamente agora saem como `[redacted]` em ambos os casos. **Não alterado**: a
  decisão de continuar incluindo `attempts`/`safe_error` na resposta HTTP ao chamador anônimo de
  `/tempo-real` quando os 4 provedores falham — isso é comportamento de diagnóstico existente, útil pro
  vendedor entender a falha; a redação agora cobre os formatos de chave relevantes, reduzindo o risco sem
  precisar remover a informação de diagnóstico.
- **Severidade original**: HIGH
- **Severidade**: HIGH
- **Evidência**: `api/ai_router.py:421-428`
  ```python
  def _safe_error(error: Exception) -> str:
      message = f"{type(error).__name__}: {error}"
      message = re.sub(r"sk-[A-Za-z0-9_\-]+", "[redacted]", message)
      message = re.sub(r"(?i)(api[_-]?key|token|password|secret)=\S+", r"\1=[redacted]", message)
      message = re.sub(r"(?i)(authorization|bearer)\s+[A-Za-z0-9_\-\.]+", r"\1 [redacted]", message)
  ```
  Essa função **existe deliberadamente** para o cenário descrito na tarefa (exception de lib de API vazando a key usada) e cobre bem `sk-...` (OpenAI/Anthropic) e cabeçalhos `Authorization`/`Bearer`. Porém não tem padrão para o formato de chave do Google (`AIza[0-9A-Za-z_-]{35}`, usada via `GOOGLE_API_KEY`/`GEMINI_API_KEY`, `api/ai_router.py:364`) nem para o parâmetro de URL `?key=...` que o SDK `google.generativeai` usa para autenticar (`_call_gemini`, `api/ai_router.py:321-337`) — o regex de `key=` exige literalmente `api_key`/`api-key`/`apikey`, não a palavra solta `key`.
  O resultado (`attempts`, contendo `safe_error`) é embutido diretamente em `HTTPException(503).detail["provedores_tentados"]` (`api/ai_router.py:750-755`) — devolvido na resposta HTTP a **qualquer chamador** de `/tempo-real` (sem autenticação obrigatória) quando os 4 provedores centrais falham simultaneamente. CLAUDE.md confirma que esse cenário **já ocorreu em produção** ("incidente de saldo/chave inválida... 31/08/2026").
- **Impacto**: Numa falha simultânea dos 4 provedores em que o erro do Gemini contenha a URL da requisição com a chave, a chave `GOOGLE_API_KEY` real vazaria na resposta HTTP para qualquer usuário anônimo do endpoint `/tempo-real`.
- **Correção recomendada**: Adicionar ao `_safe_error` um padrão para `AIza[0-9A-Za-z_-]{35}` e para `[?&]key=\S+`; considerar não incluir `attempts` bruto na resposta ao cliente (só logar/observability), devolvendo apenas uma mensagem genérica.

### H6 — Nenhuma proteção contra força bruta em `/auth/login`

- **Status**: **CORRIGIDO em 08/09/2026** — adicionado bloqueio em memória por e-mail: 5 tentativas falhas
  em 15 minutos bloqueiam novas tentativas para aquele e-mail por 15 minutos (`HTTPException(429)`), contador
  reseta em login bem-sucedido. Mesmo padrão de estado em memória por processo já usado pelo circuit breaker
  de `api/ai_router.py` e pelo cache de `api/otimizacao.py` neste projeto. Verificado isoladamente (função
  pura, sem depender de banco): 5 falhas bloqueiam a 6ª tentativa com 429, sucesso reseta o bloqueio. Não foi
  possível testar o fluxo HTTP completo (`POST /auth/login` de ponta a ponta) neste ambiente porque
  `agent/sessao_manager.py` usa PyMySQL direto sem fallback SQLite (diferente de `api/database.py`) e esta
  máquina não tem acesso direto ao MySQL da VPS — mesma lacuna de ambiente já registrada no inventário
  (MOD-01 sem nenhum teste). **Limitação conhecida**: estado em memória por processo — se o serviço rodar
  com múltiplos workers uvicorn, o contador não é compartilhado entre eles (mesma limitação já aceita pelo
  projeto para o circuit breaker/cache de custo).
- **Status original (antes da correção)**: Vulnerável
- **Severidade**: HIGH
- **Evidência**: `api/main.py:2700-2739`. Busca por `tentativas`/`lockout`/`bloqueado` em `api/` não encontrou nenhum mecanismo de contagem de tentativas falhas, e (como em H4) não existe rate limiting em nenhum lugar da aplicação.
- **Impacto**: Um atacante pode tentar senhas ilimitadamente contra qualquer e-mail cadastrado (inclusive `phpos35@gmail.com`, o admin documentado em CLAUDE.md), limitado apenas pelo custo computacional do bcrypt no servidor — sem bloqueio de conta, sem CAPTCHA, sem atraso progressivo.
- **Correção recomendada**: Adicionar rate limiting por IP/e-mail em `/auth/login` (ex.: `slowapi`) e um contador de tentativas falhas com bloqueio temporário por conta.

---

## MEDIUM

### M1 — XSS armazenado: `escHtml()` não escapa aspas simples, e `meeting_id` é aceito sem validação de formato

- **Status**: **CORRIGIDO em 08/09/2026**. `escHtml()` (`frontend/dashboard.html`) agora também escapa `'`
  (`&#39;`) — fecha o vetor de quebra de atributo `onclick="fn('${escHtml(x)}')"` diretamente, independente
  de qualquer validação de formato no backend. Adicionalmente, `POST /clientes/{id}/reunioes`
  (`api/main.py::vincular_reuniao_endpoint`) passou a validar `meeting_id` contra `^[\w.\-: ]+$` — bloqueia
  aspas/`<`/`>`/barra invertida sem exigir o formato estrito de código do Meet (que quebraria IDs vindos do
  fallback do webhook Tactiq, ex. `completa_20260908_123456`). Verificado com `TestClient`:
  `abc-defg-hij` e `completa_20260908_123456` passam (200), `x'onclick=alert(1)` e `<script>` são
  rejeitados (400).
- **Severidade original**: MEDIUM (impacto alto — roubo de token — mas exige um usuário autenticado como vetor de entrada)
- **Evidência**:
  - `frontend/dashboard.html:5201-5204`:
    ```js
    function escHtml(t) {
      if (typeof t !== 'string') return String(t ?? '');
      return t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    ```
    Não escapa `'` (aspas simples).
  - `frontend/dashboard.html:3972` usa o valor escapado dentro de um atributo `onclick` delimitado por aspas simples:
    ```js
    <button onclick="desvinculaReuniaoCliente('${cid}','${escHtml(r.meeting_id)}')" ...>
    ```
    Um `meeting_id` contendo `'` quebra o atributo e permite injetar JavaScript arbitrário no contexto de qualquer usuário que abra a página de detalhe daquele cliente.
  - `r.meeting_id` chega sem qualquer validação de formato via `POST /clientes/{client_id}/reunioes` (`api/main.py:1224-1249`, só `_req_auth`, sem regex) — ao contrário de `/cenario/{meeting_id}` e `/api/cenario/{meeting_id}` (`api/main.py:2331-2356`), que **exigem** o formato de código do Meet (`^[a-z]{3}-[a-z]{4}-[a-z]{3}$`).
  - O token JWT é guardado em `localStorage` (`frontend/login.html:539: localStorage.setItem('saleia_token', d.token)`), lido por praticamente toda chamada autenticada do dashboard (`frontend/dashboard.html:1843` etc.) — acessível a qualquer JS injetado com sucesso na mesma origem.
- **Impacto**: Um usuário autenticado (mesmo perfil "operador") pode vincular à sua própria carteira de clientes um `meeting_id` malicioso; se um admin (ou outro vendedor) abrir a tela de detalhe desse cliente, o JS injetado roda no contexto dele e pode ler `localStorage.saleia_token`, permitindo personificar essa vítima (inclusive escalada de privilégio se a vítima for admin) por até 72h (validade do JWT).
- **Correção recomendada**: Escapar também `'` (e idealmente usar `textContent`/atributos `data-*` com `addEventListener` em vez de construir `onclick="...('${...}')"` via string). Adicionalmente, validar o formato de `meeting_id` no backend em todos os endpoints que o recebem, não só em `/cenario`.

### M2 — Detecção de prompt injection é baseada em poucos regex, facilmente contornável

- **Status**: **AMPLIADO em 08/09/2026** (ainda não é detecção robusta por modelo dedicado, mas cobre bem
  mais que os 6 padrões originais). `_INJECTION_PATTERNS` (`services/knowledge_compiler/sanitizer.py`)
  passou de 6 para 19 padrões: variações PT/EN de "ignore/desconsidere/esqueça instruções",
  "disregard"/"forget previous", marcador de role `user:` (além de `system:`/`assistant:`/`developer:`),
  troca de persona ("from now on you are"/"a partir de agora você é"), tentativa de exfiltrar o prompt
  ("reveal/print system prompt"/"revele o prompt") e marcadores de formato de jailbreak (`[INST]`,
  `<|im_start|>`, `-----BEGIN SYSTEM`). Testado contra 3 frases legítimas de conteúdo comercial (incluindo
  uma frase deliberadamente parecida com o novo padrão "a partir de agora" para forçar um quase-falso-
  positivo) — nenhuma foi sinalizada — e 6 tentativas de injeção (PT/EN/marcadores de formato) — todas
  foram sinalizadas. Suíte completa de `test_knowledge_compiler_*` (50 testes) sem regressão.
- **Severidade original**: Parcialmente mitigado (comportamento de bloqueio confirmado; detecção fraca)
- **Severidade**: MEDIUM
- **Evidência**: `services/knowledge_compiler/sanitizer.py:16-23` — 6 padrões regex (`ignor[ae]...instru`, `system:`, `assistant:`, `developer:`, `you are now`, `você agora é`). Qualquer variação (sinônimos, outro idioma, quebra de palavra, injeção via caractere invisível diferente das categorias Unicode `C*` removidas) passa despercebida.
  **Confirmado positivamente** (contrariando a possibilidade, levantada pela tarefa, de que a Fase 2 só marca sem bloquear): `services/knowledge_compiler/compiler.py:55-65` (`_secoes_compilaveis`) efetivamente **pula** (não processa com IA) qualquer seção com a flag `potential_instruction_injection` — o comportamento descrito no CLAUDE.md para a Fase 2 está implementado corretamente no código, não é só uma intenção de doc.
- **Impacto**: Como a primeira linha de detecção é fraca, a maior parte de tentativas reais de prompt injection em documentos da Biblioteca de Inteligência provavelmente nunca chegaria a ser sinalizada — o bloqueio da Fase 2 só protege o que a Fase 1 detecta.
- **Correção recomendada**: Ampliar os padrões (multilíngue, incluir variações comuns de jailbreak), e/ou complementar com uma checagem por um modelo classificador dedicado antes da compilação, já que o texto de qualquer forma passa por um LLM na Fase 2.

### M3 — Upload de documentos valida só extensão do nome do arquivo, não o conteúdo real

- **Status**: **CORRIGIDO em 08/09/2026** para PDF e DOCX (os 2 formatos binários com assinatura
  verificável). `_validar_magic_bytes()` (`api/main.py`) confere `%PDF-` para `.pdf` e `PK\x03\x04` (ZIP/
  OOXML) para `.docx`, chamada em `POST /base` e `POST /biblioteca/fontes` antes de gravar o arquivo em
  disco — devolve 415 se a assinatura não bater com a extensão declarada. **Decisão deliberada**: não usei
  `python-magic` (exigiria `libmagic` no SO, não confirmado que está disponível/testado na VPS) — checagem
  de assinatura manual, sem dependência nova. TXT/MD/HTML continuam validados só por extensão (são texto
  livre por natureza, sem assinatura binária própria pra checar — mesma limitação, não piorou nem
  melhorou). Verificado: conteúdo `%PDF-1.4...` com extensão `.pdf` passa; texto puro renomeado para `.pdf`
  é rejeitado (415); mesmo padrão para `.docx`/`PK\x03\x04`.
- **Severidade original**: Parcialmente mitigado
- **Severidade**: MEDIUM
- **Evidência**: `api/main.py:2102-2105` (`POST /biblioteca/fontes`) e `:1963-1973` (`POST /base`) verificam apenas a extensão do nome do arquivo (`ext not in ("pdf","docx","txt","md","markdown","html","htm")`) e armazenam `arquivo.content_type` (declarado pelo cliente, não verificado) — nenhum dos dois confere magic bytes/assinatura real do arquivo antes de repassá-lo a `pypdf`/`pdfplumber`/`python-docx`/BeautifulSoup4 (`services/knowledge_compiler/extractors/base.py` despacha só por `mime_type`/`filename`, ambos vindos do cliente).
  O nome do arquivo em si **é** tratado corretamente contra path traversal: `re.sub(r"[^A-Za-z0-9._-]+", "_", nome_arquivo)[:150]` + prefixo `uuid4().hex` (`api/main.py:2121-2122`, `:1967-1968`) — qualquer `../` é neutralizado antes de virar nome de arquivo em disco.
- **Impacto**: Um arquivo malformado/malicioso renomeado com extensão permitida é aceito e entregue às bibliotecas de parsing (superfície de ataque da própria lib), mesmo que seu conteúdo real não corresponda ao tipo declarado. Risco limitado porque o arquivo nunca é executado no servidor, só parseado como texto.
- **Correção recomendada**: Validar magic bytes reais (ex.: `python-magic`) antes de despachar ao extractor, e sandboxar/limitar timeout do parsing.

---

## LOW

### L1 — Endpoints que recebem `body: dict` cru podem lançar exceção não tratada com tipos inesperados

- **Status**: **CORRIGIDO em 08/09/2026 para os 4 pontos com crash confirmado** (não um refactor completo
  pra Pydantic — risco maior em 8 endpoints de produção por um ganho pequeno, dado que o handler padrão do
  FastAPI já não vaza traceback). `criar_cliente_endpoint`, `atualizar_status_relatorio`,
  `vincular_reuniao_endpoint`, `gerar_skill_endpoint`: campos que chamavam `.strip()`/`.lower()` direto em
  `body.get(...)` agora passam por `str(...)` antes — um valor não-string (ex. `{"nome": 123}`) não quebra
  mais com `AttributeError` não capturado, vira uma string válida que a validação de negócio trata
  normalmente. `atualizar_followup_endpoint` ganhou `TypeError` no `except` por precaução, mas investigando
  o código descobri que `agent/followup_generator.py::atualizar_followup(fid, **kwargs)` já filtra por
  allowlist (`campos_validos`) internamente — nunca lança `TypeError` por chave desconhecida, esse endpoint
  não tinha o bug na prática (correção defensiva, não um fix de um crash real). Os outros 3 `body: dict`
  (`atualizar_playbook_endpoint`, `atualizar_cliente_endpoint`, `atualizar_skill_endpoint`) repassam o dict
  inteiro pra uma função downstream sem tocar em campos individuais no handler — o risco, se existir, está
  na camada `agent/*.py`, fora do escopo desta correção pontual. Verificado com `TestClient`: `nome=123`/
  `status=999`/`meeting_id=456`/`contexto=42` não quebram mais com erro não tratado (chegam à validação de
  negócio normal, com 400 quando aplicável).
- **Severidade original**: Vulnerável (impacto baixo)
- **Severidade**: LOW
- **Evidência**: 8 ocorrências de `body: dict` (em vez de um `BaseModel` do Pydantic) em `api/main.py`, linhas 1006, 1075, 1151, 1191, 1227, 1301, 1322, 1561. Exemplo concreto — `criar_cliente_endpoint` (`api/main.py:1150-1169`):
  ```python
  def criar_cliente_endpoint(body: dict, authorization: str | None = Header(default=None)):
      _req_auth(authorization)
      nome = (body.get("nome") or "").strip()   # fora do try/except abaixo
  ```
  Se `body = {"nome": 123}`, `123 or ""` é truthy (`123`), e `.strip()` num `int` lança `AttributeError` não capturado (a linha está antes do `try:` que começa em 1157) — resulta em 500 genérico do FastAPI em vez do 422 automático que um `BaseModel` Pydantic daria.
- **Impacto**: Baixo — não vaza dados sensíveis (handler padrão do FastAPI não expõe traceback), mas é uma inconsistência de validação de entrada num sistema que, na maior parte, usa Pydantic corretamente (proteção automática contra tipos malformados).
- **Correção recomendada**: Substituir esses `body: dict` por `BaseModel`s dedicados, replicando o padrão já usado em `TempoRealRequest`/`AuthLoginRequest`/etc.

### L2 — Permissão `tabs` da extensão Chrome mais ampla do que o uso observado exige estritamente

- **Status**: **CORRIGIDO em 08/09/2026, validado empiricamente** — não só por leitura de código. Este
  ambiente tem Chrome real instalado (`C:\Program Files\Google\Chrome\Application\chrome.exe`) e Playwright
  disponível (dependência transitiva do `promptfoo`); usei os dois para carregar a extensão de verdade num
  Chrome real via `launchPersistentContext` com `--load-extension`, interceptando só a navegação para
  `meet.google.com` com uma página local fake (`context.route`, nunca contata o Google de verdade) — sem
  precisar de conta/reunião real. Comparei o comportamento com e sem a permissão `tabs` no manifest:
  `chrome.tabs.query({url: 'https://meet.google.com/*'})` (usado por `propagarParaMeet` e roteamento de
  áudio) e o indicador visual (`chrome.tabs.onActivated`/`onUpdated` → badge verde/cinza via `ehUrlDoMeet`)
  disparado por troca de aba **real** (`page.bringToFront()`) — resultado **idêntico** nos dois casos:
  mesma URL retornada pela query, badge "●" na aba do Meet e "" na aba em branco, nos dois manifests.
  Removida a permissão `tabs` de `chrome-extension/manifest.json`; versão da extensão `1.4.8` → `1.4.9`.
  **Requer ação do usuário**: mudanças em `chrome-extension/` não são deployadas como o backend — cada
  vendedor precisa reinstalar a extensão manualmente no navegador (`CLAUDE.md`), não é algo que eu resolvo
  via SSH/git pull.
- **Severidade original**: Aceitável, mas não minimalista
- **Severidade**: LOW
- **Evidência**: `chrome-extension/manifest.json:6` declara `"permissions": ["activeTab", "storage", "alarms", "offscreen", "tabs", "tabCapture"]`. O uso real de `chrome.tabs.*` (`chrome-extension/background.js:242,262,290-301`; `chrome-extension/popup.js:135`) fica limitado a consultar/mensagear abas do `meet.google.com` e observar `onActivated`/`onUpdated` — funcionalidade que, em grande parte, já é coberta pelos `host_permissions` declarados para `https://meet.google.com/*`. `tabs` concede visibilidade a título/URL de **todas** as abas abertas do usuário, não só as do Meet.
- **Impacto**: Superfície de consentimento desnecessariamente ampla na tela de instalação da Chrome Web Store; não há, no código lido, nenhum uso que efetivamente leia ou exfiltre dados de abas fora do Meet — não é uma vulnerabilidade explorável, é sobre-permissão.
- **Correção recomendada**: Reavaliar se `activeTab` + os `host_permissions` já existentes bastam para os handlers de `chrome.tabs.onActivated`/`onUpdated`; remover `tabs` se sim.

---

## Controles confirmados como corretamente implementados

Para não superestimar os achados, seguem os pontos auditados que **não** apresentaram falha:

1. **SQL Injection — nenhuma instância explorável encontrada.** Toda construção dinâmica de SQL (`f"UPDATE tabela SET {cols} WHERE id=%s"`, `f"... IN ({placeholders})"`) usa nomes de coluna vindos de allowlists fixas no código (`_EDITAVEIS`/`campos_validos`) ou tuplas hardcoded, nunca de chaves de request arbitrárias — e todo valor é sempre passado via `%s` parametrizado. Verificado em `agent/client_intelligence.py:184-214`, `agent/sales_memory.py:292-328`, `agent/playbook_generator.py:282-339`, `agent/skill_resolver.py:481-506`, `agent/followup_generator.py:255-269`, `agent/sessao_manager.py:289-307,489-513`.
2. **Fluxo de recuperação de senha bem construído**: resposta neutra (não revela se o e-mail existe), token com `secrets.token_urlsafe(32)`, expiração de 1h, e é **de uso único** (`reset_token=NULL` após o uso) — `api/main.py:2783-2946`.
3. **JWT decodificado com algoritmo fixo** (`algorithms=["HS256"]`) — sem vulnerabilidade de confusão de algoritmo/`alg: none` — `api/main.py:3033,3047`.
4. **`.env` corretamente no `.gitignore` e nunca commitado** (`git ls-files | grep -i "\.env"` só retorna `.env.example`, que contém apenas placeholders como `sk-your-key-here`). Nenhuma chave real (`sk-`, `AIza`, `gsk_`) encontrada em nenhum `.py`/`.js`/`.html` versionado.
5. **`CLAUDE_TOKEN_ENC_KEY` falha fechado corretamente** se ausente (`agent/claude_account.py:120-127`) — o padrão certo que deveria ter sido replicado para `JWT_SECRET` (ver C1).
6. **`_safe_error` existe deliberadamente e cobre a maioria dos casos** (`sk-...`, `Authorization`/`Bearer`, `api_key=`/`token=`/`password=`/`secret=`) — gap específico documentado em H5, mas o mecanismo em si é uma defesa real, não ausente.
7. **Extensão Chrome não expõe URL do backend, provedor de IA nem score numérico na UI visível** — confirmado por grep no `content.js`/`popup.js`/`popup.html`: a sidebar renderiza só `propensao.nivel` (Alta/Média/Baixa/texto), nunca `score_compra` numérico; `backendAtual()` é usado só internamente para `fetch`/`tabs.create`, nunca escrito como `textContent` visível. `host_permissions` não usa `<all_urls>`.
8. **`/tempo-real` nunca quebra com token ausente/inválido/expirado** — `_req_auth` é chamado dentro de um `try/except HTTPException: pass` específico (`api/main.py:670-675`), garantindo degradação graciosa para uso anônimo em vez de 401/500, conforme documentado no CLAUDE.md.
9. **Sanitização de nome de arquivo em upload sem possibilidade de path traversal** — `re.sub(r"[^A-Za-z0-9._-]+", "_", nome)` + prefixo UUID em ambos `/base` e `/biblioteca/fontes` (ver M3 para a ressalva sobre validação de conteúdo).
