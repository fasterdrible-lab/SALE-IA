# Plano — Legenda em tempo real + gravação como rede de segurança

Criado em 15/10/2026, a partir da avaliação de produção da mesma data.
Uma tarefa por vez, com aprovação entre elas. Tudo que mexe em produção
(VPS, banco, `.env`, deploy) precisa de "sim" explícito antes.

## Por que mudar

Números de produção (11 a 14/10, 17 reuniões, 8 gravadas):

- A legenda do Meet cobre **88%** do que o áudio transcreveu e chega a
  130–170 palavras/min. Para o coach em tempo real, o conteúdo basta.
- O que falta na legenda é **quem falou**: a maioria das linhas sai
  "Não identificado".
- Transcrever áudio em tempo real foi o que custou caro: travou a VPS em
  14/10 (Whisper local em CPU) e esgotou a cota grátis do Groq no mesmo
  dia (1.289 erros 429; ~8 h de reunião).
- O áudio sobe **duas vezes**: blocos da gravação (`/gravacao/bloco`) +
  ciclos para transcrição (`/audio-transcricao`).
- A gravação a 128 kbps gasta ~0,9 GB/dia; com 90 dias de retenção, ~80 GB.
- O MySQL está com 17 GB, quase tudo **binlog** (~2 GB/dia, retenção de
  30 dias) — vem da transcrição regravada inteira a cada ciclo, não da
  gravação.

## Como fica

| Momento | Fonte | Para quê |
|---|---|---|
| Durante a reunião | Legenda do Meet + falante pelo volume do microfone (no navegador) | Coach e agentes em tempo real |
| Depois da reunião | Gravação de cada trilha (microfone = vendedor, aba = cliente) transcrita uma vez | Relatório, histórico, RAG, painel 🎧 |

Nenhuma transcrição de áudio durante a chamada. A gravação vira a única
fonte de áudio e a garantia de que nada se perde.

## Impacto no roteiro Audio-First (`docs/PROMPT_MESTRE_AUDIO_FIRST.md`)

- **T03** (faster-whisper incremental em tempo real): substituída por
  este plano — não fazer.
- **T05** (identificação de participantes): a parte mic × aba é a
  tarefa 2.1 daqui; diarização dentro da aba fica para depois.
- **T09** (transcrição definitiva pós-reunião): antecipada como Fase 3.
- T04, T06–T08, T10–T12 seguem valendo, depois deste plano.

**Precisa de aprovação do usuário antes de começar.**

---

## Fase 0 — Operação (sem código)

### 0.1 IA de volta ao ar
- Recarregar o DeepSeek (sem saldo desde 14/10 21:03 UTC). Consumo de
  14/10: ~US$ 2,60/dia com 5 reuniões.
- Decidir se a conta Claude pessoal continua como reserva: custou
  ~US$ 25 estimados em ~41 chamadas em 14/10.
- **Pronto quando**: `/health` com `ia_disponivel: true`.

### 0.2 Binlog do MySQL
- `SET PERSIST binlog_expire_logs_seconds = 259200` (3 dias) e
  `PURGE BINARY LOGS BEFORE NOW() - INTERVAL 3 DAY`. O backup diário
  (dump 05:30 UTC, 14 dias) cobre a recuperação.
- **Pronto quando**: `/var/lib/mysql` < 7 GB e a variável persistida
  depois de reiniciar o MySQL.
- **Feita 15/10/2026 ~12:28 UTC** (aprovada pelo usuário): MySQL 8.4,
  sem réplica, backup das 05:30 conferido. `SET PERSIST` gravado em
  `mysqld-auto.cnf`; 189 → 44 binlogs; `/var/lib/mysql` 17 GB → 4,7 GB;
  disco livre 113 → 125 GB; `/health` online. No mesmo horário a IA já
  estava de volta (`ia_disponivel: true`) — 0.1 feita pelo usuário.

---

## Fase 1 — Cortar custo sem perder nada

### 1.1 Gravação a 32 kbps + retenção de 30 dias
- Extensão: `audioBitsPerSecond` vindo do servidor (`/gravacao/config`,
  novo campo `bitrate`, padrão 32000) nos dois gravadores:
  `chrome-extension/gravacao_rules.js` (`criarGravadorContinuo`, trilha do
  microfone, chamado por `content.js`) e a trilha da aba em
  `chrome-extension/offscreen.js`.
- Servidor: `GRAVACAO_RETENCAO_DIAS=30` (já existe em
  `agent/gravacao_rules.py`, padrão 90). Vale para gravações novas;
  as existentes mantêm o `apagar_em` (decidir se encurta).
- **Testes**: config com bitrate; bloco a 32 kbps passa na integridade
  (`verificar_integridade`); painel 🎧 toca normalmente.
- **Pronto quando**: gravação real com ~14 MB/h por trilha (era ~58 MB/h)
  e áudio inteligível no painel.

### 1.2 Desligar a transcrição de áudio em tempo real
- Servidor: novo kill-switch `TRANSCRICAO_TEMPO_REAL_ATIVA` (padrão
  `false`); `/gravacao/config` (ou o heartbeat) informa a extensão.
- Extensão: com a chave desligada, não abre os ciclos de
  `/audio-transcricao` (`content.js` microfone; `background.js` /
  `offscreen.js` aba). A gravação continua igual.
- `/audio-transcricao` responde sem transcrever quando desligado (cobre
  extensões antigas ainda instaladas).
- **Pronto quando**: reunião real com zero chamadas ao Whisper/Groq,
  gravação completa e transcrição da legenda normal.

### Situação 1.1 + 1.2 (15/10/2026)
- **V.1.4.180 em produção** (`dd9b8db` = VPS HEAD, deploy 17:24 UTC por
  bundle, sem reunião ativa; `NRestarts=0`). Suíte completa local: 1.979
  testes OK. Conferido depois do deploy: `/gravacao/config` =
  `bitrate 32000, retencao_dias 7, transcricao_tempo_real false`;
  `/audio-transcricao` = `tempo_real_desligado`; 10 pedidos de extensões
  antigas depois do restart, 0 chamadas à Groq.
- **Ext 1.4.26** em `chrome-extension.zip` (e cópia `chrome-extension.
  V.1.4.26.zip` na pasta de cima): **falta reinstalar nos vendedores**.
  Até lá a gravação continua a 128 kbps (o bitrate é aplicado pela
  extensão) e as extensões antigas seguem subindo pedaços que o servidor
  ignora.
- Achado: o limite da Groq que estourou também é de **2.000 pedidos por
  dia** (RPD), não só de segundos de áudio — relevante para a 3.1
  (mandar pedaços longos, não de 15 s).

---

## Fase 2 — Qualidade da legenda em tempo real

### 2.1 Falante pelo volume do microfone (principal ganho)
- No `content.js`, um `AnalyserNode` no stream do microfone (o mesmo da
  gravação) registra uma linha do tempo de "voz no microfone" (RMS acima
  do limiar, com ~300 ms de folga).
- Ao confirmar uma linha de legenda (`commitarFrase`), calcular a
  fração do intervalo da fala (do 1º aparecimento até a confirmação, com
  ~1,5 s de atraso da legenda) em que o microfone tinha voz:
  - ≥ 60% → vendedor;
  - ≤ 20% → cliente (nome do cliente se houver um só; senão "Cliente");
  - entre os dois → "Não identificado".
- Nome real vindo da legenda (quando o Meet mostra) continua tendo
  prioridade.
- Função pura em `chrome-extension/transcricao_rules.js` + testes Node em
  `tests/js/test_extensao_transcricao.js`.
- Cuidados: eco do alto-falante no microfone (o Chrome já cancela eco
  por padrão; conferir), microfone mudo no Meet (= não é o vendedor),
  fala sobreposta (cai no "Não identificado").
- **Validação sem trabalho manual**: script na VPS cruza o rótulo de cada
  linha com o volume da trilha do microfone no mesmo horário
  (`gravacoes_niveis`) e mede a % de acerto.
- **Pronto quando**: < 15% de "Não identificado" e ≥ 90% de acerto
  vendedor × cliente numa reunião real.

### 2.2 Repetições que sobraram (7–9% pós-V.1.4.178)
- Legenda parcial que cresce ("E aí hoje assim?" → "E aí hoje assim a
  minha família…"): a nova substitui a anterior quando a contém como
  prefixo (extensão `decidirCommit` + backend).
- Bloco reenviado fora de sequência (4 falas repetidas mais adiante):
  ampliar a regra de bloco reenviado para blocos não adjacentes.
- Limpar `iyz-hvkc-ctt` no banco (40% duplicada) com backup antes.
- **Pronto quando**: < 2% de linhas repetidas em reunião nova; script de
  avaliação de 15/10 rodado de novo.

### 2.3 Medir a legenda
- Usuário salva ~10 min de trechos de referência no painel 🎧
  (ouvindo a gravação). Dá o 1º WER real da legenda do Meet.
- Conferir que a legenda está em português nos vendedores.
- **Pronto quando**: WER da legenda registrado em `gravacoes_referencias`.

---

## Fase 3 — Transcrição definitiva pós-reunião (antecipa a T09)

### 3.1 Fila de transcrição das gravações
- Quando a reunião termina (todas as gravações `encerrada`, alguns
  minutos sem bloco novo), entra numa fila com **um processo por vez**.
- Transcreve a trilha da aba (cliente) e a do microfone (vendedor) com
  horário por segmento. Falante sai de graça: cada trilha é um lado.
- Provedor: Groq respeitando 7.200 s/h e 28.800 s/dia (espera e retoma
  quando bater o limite) **ou** Whisper local com prioridade baixa
  (`nice`), um de cada vez, fora do horário de reunião. Decisão do
  usuário (ver abaixo).
- Tabela nova `transcricao_definitiva` (meeting_id, trilha, início,
  fim, texto).
- **Pronto quando**: reunião real transcrita sozinha depois de terminar,
  sem afetar `/health` nem outra reunião em andamento.

### 3.2 Usar a transcrição definitiva
- Relatório final, histórico, exportação para o RAG e painel 🎧 passam
  a ler a definitiva quando existir (legenda continua como reserva).
- Glossário (`TRANSCRICAO_GLOSSARIO`) e nomes dos participantes no
  prompt do Whisper para acertar nomes e termos do negócio.
- **Pronto quando**: relatório de uma reunião real gerado da definitiva,
  com WER menor que o da legenda nos trechos de referência da 2.3.

### 3.3 Comparar e apagar (sugestão do usuário, 15/10)
- Depois da 3.1, cada reunião ganha um relatório de comparação
  legenda × transcrição definitiva: concordância de texto (WER da
  legenda tomando a definitiva como base), acerto do falante da 2.1
  (rótulo da legenda × trilha que tinha voz) e trechos que só a
  gravação pegou. Fica salvo no banco (pequeno, sem áudio) e alimenta
  a média de qualidade ao longo do tempo.
- Feita a comparação, o áudio é apagado depois de um prazo curto
  (sugestão: 7 dias, para ouvir/conferir algo recente). Ficam mais
  tempo só:
  - reuniões com divergência alta (ex.: concordância < 80% ou
    falante < 85%) — até alguém revisar no painel 🎧;
  - trechos marcados como referência (`gravacoes_referencias`) — são
    o gabarito.
- A transcrição definitiva e o relatório de comparação ficam; o que se
  perde é só poder retranscrever com um modelo melhor no futuro.
- Ganho: disco quase constante (~1–2 GB) e menos dado sensível guardado
  (LGPD).
- Ressalva: a definitiva também tem erro (é Whisper, não gabarito). O
  número que mede a verdade continua vindo dos trechos de referência
  feitos à mão (2.3); a comparação automática serve para achar as
  reuniões ruins.
- **Pronto quando**: reunião real comparada, áudio apagado no prazo,
  reunião com divergência alta mantida e visível no painel.

---

## Fase 4 — Banco

### 4.1 Parar de regravar a transcrição inteira a cada ciclo
- Hoje `meeting_memory.transcript_full` e `sessoes.transcricao_acumulada`
  (até 280 mil caracteres) são regravados a cada 20 s → ~2 GB/dia de
  binlog.
- Gravar só as linhas novas (tabela de falas, só INSERT) e montar o
  texto na leitura. Converge com a T04 (consolidação e deduplicação).
- **Pronto quando**: binlog < 300 MB por dia com o mesmo volume de
  reuniões.

---

## Decisões do usuário

1. Aprovar a mudança do roteiro (T03 sai, T09 antecipada).
2. ~~Retenção das gravações~~ **7 dias, inclusive as já gravadas**
   (15/10): `GRAVACAO_RETENCAO_DIAS=7` no `.env` da VPS (backup
   `.env.bak_retencao7_*`) e `apagar_em = iniciada_em + 7 dias` nas 133
   existentes. A limpeza de hora em hora apaga a 1ª em 18/10 19:43 e as
   de 14/10 em 21/10. Na 1.1 o padrão do código passa a 7 também. Para
   a 3.3, o "prazo curto" já é esse.
3. Transcrição pós-reunião: Groq grátis com fila (pode atrasar em dias
   de muitas reuniões), Groq pago, ou Whisper local fora do horário?
4. ~~Conta Claude pessoal continua como reserva de IA?~~ **Não** (15/10):
   `CLAUDE_ACCOUNT_PILOT=false` na VPS (backup
   `.env.bak_claude_off_*`). Histórico: ~US$ 142 estimados desde 03/09,
   só como reserva; a "análise sob demanda" nunca foi usada.

## Ordem sugerida

0.1 → 0.2 → 1.1 + 1.2 (uma versão de extensão só) → 2.1 → 2.2 → 2.3
(usuário, em paralelo) → 3.1 → 3.2 → 3.3 → 4.1.

Cada versão de extensão exige reinstalar nos vendedores — juntar 1.1,
1.2 e, se possível, 2.1 no mesmo pacote.
