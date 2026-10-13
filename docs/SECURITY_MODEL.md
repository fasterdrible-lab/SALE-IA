# SALEIA — Modelo de Segurança

> Seção 35 do "PROMPT MESTRE — SALE-IA V2" (Tarefa D9). Criado na
> V.1.4.164 (05/10/2026); revisado em **V.1.4.175 (13/10/2026)** com a
> gravação de áudio, o painel de Gravações e um levantamento da VPS.
> Inclui as lacunas conhecidas. Este arquivo fica só no repositório; o
> Dev Manual (`/manual-tecnico`, só admin desde a V.1.4.176) não repete
> os detalhes da seção 7.

## 1. Autenticação e sessão

- **JWT HS256** (`api/main.py`), segredo em `JWT_SECRET` no `.env`
  (a aplicação não sobe sem ele). Validade de **72h**.
- **Sessão deslizante** (B8): faltando menos de 24h, `/tempo-real`
  devolve `token_renovado`; a resposta traz `auth_status`
  (`ok`/`anonimo`/`expirado`/`invalido`) e a extensão faz logout quando
  expira.
- Senhas com **bcrypt**. Recuperação por token de 1h
  (`secrets.token_urlsafe`) enviado por SMTP; resposta sempre neutra (não
  revela se o e-mail existe).
- Perfis: `admin` e `operador`. Rotas `/admin/*` exigem `_req_admin`.
- **Bloqueio de login**: 5 tentativas falhas por e-mail → 15 min
  bloqueado (em memória, por processo).

## 2. Isolamento de dados (Fase 18.1)

- `MeetingMemory.usuario_id` é carimbado na primeira gravação com
  usuário logado e nunca sobrescrito. `_verificar_dono_ou_admin()`
  restringe a reunião ao dono ou a admin.
- **Lacuna**: reuniões anônimas (extensão sem login) ou anteriores à
  Fase 18 não têm dono e ficam visíveis a qualquer usuário autenticado.
- **Gravações (T02) e painel de Gravações**: áudio, volume, trechos de
  referência e transcrição mostrada no painel só para o dono da gravação
  ou admin; gravação de outra pessoa responde 404 (não confirma que
  existe). Editar/apagar trecho de referência: só o autor ou admin.
- Não há multi-tenancy: o SALEIA é de uso interno de uma empresa
  (decisão registrada em `KnowledgeSource`). A Base de Conhecimento é
  global.

## 3. Segredos

- Chaves de IA, banco, SMTP, Telegram e JWT ficam só no `.env` da VPS.
  O frontend e a extensão nunca recebem chave; `/admin/api/provedores`
  devolve a chave mascarada.
- **Redação em log** (18.3): `redigir_segredos()` roda no
  `_JsonFormatter`, o choke-point de todo log da aplicação. Mascara
  senha, token, `Authorization: Bearer`, chaves de API.
- Token OAuth da conta Claude pessoal é gravado criptografado
  (`claude_connections.oauth_token_encrypted`).

## 4. Prompt injection e IA (18.2, Fase 21)

- Transcrição e documentos são **dados, nunca instruções**:
  `PROMPT_INJECTION_GUARD_TEXT` é anexado a todo system prompt em
  `api/ai_router.py::chamar_ia` (e replicado em `claude_fallback.py`).
- `detectar_tentativas_injection()` (regex PT/EN: "ignore as regras",
  marcadores de papel, troca de persona, exfiltração de prompt) só
  sinaliza; cada detecção vira `PolicyViolationEvent`. Medido em
  produção: `policy_violation = 0`.
- `ADVERSARIAL_SALES_GUARD_TEXT`: nunca difamar concorrente, conceder
  desconto oculto ou garantir ROI sem base.
- Saída do motor passa por guarda de alucinação crítica e de contrato
  (ver [SALES_BRAIN_ARCHITECTURE.md](SALES_BRAIN_ARCHITECTURE.md)).

## 5. Classificação de dados (18.3)

`agent/data_classification_rules.py`: PUBLIC, INTERNAL, CONFIDENTIAL
(transcrições, diagnósticos, memórias, playbooks), PII (nome, e-mail,
telefone, nascimento, `usuario_id`), SENSITIVE (senha, token, chave).

**Gravação de áudio** (V.1.4.172+): só com login, confirmação de que os
participantes foram avisados a cada reunião e indicador visível; nunca
começa sozinha. **Retenção de 90 dias aplicada de verdade**: a
manutenção de hora em hora apaga áudio e blocos vencidos
(`api/gravacao_store.py::manutencao`).

**Lacuna**: para o resto (transcrições, diagnósticos, memórias), os
prazos de retenção (CONFIDENTIAL 365 dias, PII 180 dias) são **só
referência**. Não existe job de expiração; ficam indefinidamente.
Definir retenção real é decisão de produto/jurídica.

## 6. Auditoria

- `AuditTrailEntry` (18.4): quem, quando, ação, motivo, dados usados
  (só quais campos, nunca o conteúdo), modelo, versões de prompt/regra/
  política/conhecimento. Cobertura medida em 100% das chamadas do
  SalesReasoningEngine.
- `AuditoriaFinanceira`: toda mudança de orçamento/preço de plano.

## 7. Rede e infraestrutura

- Cloudflare na frente; nginx como proxy; uvicorn só em `127.0.0.1:8000`.
- **CORS** restrito a `api.saleia.app.br`, localhost e túneis ngrok
  (o `*` com credenciais foi removido).
- TLS por Certbot.
- **Rate limit por IP** (`_rate_limit_por_ip`, em memória, por
  processo): `/audio-transcricao` 40/min, `/gravacao/iniciar` 60/min,
  `/gravacao/bloco` 240/min. O IP vem do `X-Forwarded-For`; **confirmado
  em 13/10/2026** que o nginx da VPS repassa `X-Forwarded-For`,
  `X-Real-IP` e `X-Forwarded-Proto` (corpo máx. 20 MB, timeout 120s).
- Bloqueio de loop caro de IA por reunião (`verificar_loop_caro`,
  HTTP 429) no roteador.
- Portas abertas para fora (13/10/2026): só 22 (SSH), 80 e 443. MySQL
  (3306/33060), uvicorn (8000) e Ollama (11434) escutam só em
  `127.0.0.1`.

**Lacunas operacionais (atualizadas em 13/10/2026):**

- acesso root à VPS por **senha** (`PermitRootLogin yes` e
  `PasswordAuthentication yes` no sshd; a chave `saleia_vps` é
  recusada). Recomendado: chave SSH funcionando, depois desligar senha e
  root direto;
- **firewall (ufw) inativo**: hoje só o que escuta em 0.0.0.0 fica
  exposto (22/80/443), mas qualquer serviço novo que escute em todas as
  interfaces fica aberto. Recomendado: ufw liberando só 22/80/443 e, se
  possível, SSH restrito;
- **sem backup automático**: o único dump do MySQL é o manual de
  11/10/2026 (`/root/backups/`), na própria VPS; `data/` (gravações,
  arquivos da Base) também não tem cópia. Recomendado: dump diário +
  cópia para fora da VPS;
- o PAT do GitHub no remote de `/opt/saleia` foi recusado e apareceu num
  log de erro: precisa ser **revogado** e trocado (deploy segue por
  `git bundle`);
- a senha root passou por chat (de novo em 12/10/2026): precisa ser
  **trocada**;
- `/tempo-real` aceita reunião sem login e não passa pelo rate limit
  por IP (só pelo bloqueio de loop caro de IA);
- contadores de rate limit e de login ficam em memória por worker (2
  workers): o limite efetivo pode ser até o dobro e zera a cada restart;
- ~~Dev Manual público~~ — **resolvido na V.1.4.176**: até 13/10/2026 o
  `/manual-tecnico` era aberto e mostrava IP da VPS, acesso root por SSH,
  e-mail do admin e comandos para conferir chaves. Agora o conteúdo só
  sai de `/manual-tecnico/conteudo` com JWT de admin, e o texto não traz
  mais esses detalhes. O manual do usuário (`/manual`) segue público (não
  tem dado operacional).

## 8. Alertas de segurança e operação

Telegram (`agent/alertas.py`): banco offline/lento, taxa de erro de IA,
circuit breaker (1 por provedor/hora), orçamento, anomalia de custo,
escalonamento humano (sem cooldown).
