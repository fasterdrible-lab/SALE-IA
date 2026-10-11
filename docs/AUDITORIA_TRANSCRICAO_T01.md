# Auditoria da transcrição — TAREFA 01 (Prompt Mestre "Audio-First")

> Data: 11/10/2026 · Backend V.1.4.170 · Extensão no repo V.1.4.21 ·
> Sem mudança de comportamento. Testes de reprodução:
> `tests/test_auditoria_transcricao_t01.py` (20 testes: 16 defeitos
> reproduzidos com `expectedFailure`, 4 controles).

## 0. Fontes

- Documentos lidos: `CLAUDE.md`, `docs/CURRENT_STATE.md`, `docs/TASKS.md`
  (desatualizado desde meados de 2026), `docs/ARCHITECTURE.md`,
  `CHANGELOG.md` — todos existem.
- Código: `chrome-extension/{content,background,offscreen}.js`,
  `api/main.py` (`/tempo-real`, `/audio-transcricao`),
  `api/processador_tempo_real.py`, `api/database.py`,
  `agent/{sessao_manager,transcript_dedup_rules,ruido_interface_rules,whisper_local}.py`,
  `agent/multiagente/orquestrador.py`.
- Dados reais: cópia do backup pré-reset (`saleia_analise` na VPS, 63
  reuniões com texto desde 20/09) e `journalctl` de produção desde 01/10.

## 1. Como funciona hoje

**Captura (extensão)**

| Fonte | Onde | Como | Rótulo do falante |
|---|---|---|---|
| Legenda do Meet | `content.js::iniciarObservadorLegendas` | MutationObserver em `document.body` + varredura a cada 2s; buffer por falante, grava a frase 3,5s depois da última mudança (`commitarFrase`) | nome lido do DOM; sem nome → "Não identificado" (≥1.4.20) ou "Participante"/cliente salvo (1.4.15) |
| Microfone | `content.js::iniciarCicloWhisper` | botão na sidebar; MediaRecorder parado e reiniciado a cada 15s (+100 ms de intervalo); pedaço < 10 KB descartado | sempre "Vendedor" |
| Áudio da aba | `offscreen.js::iniciarCicloAba` | só pelo popup (exigência do `tabCapture`); ciclos de 15s | sempre "Cliente" → 1º cliente cadastrado |

Nenhum bloco de áudio tem sequência, horário de gravação ou hash. O áudio
é apagado logo depois de transcrito (`/audio-transcricao`, `finally:
os.unlink`) — não existe gravação para auditar ou reprocessar.

**Envio**

- `POST /tempo-real` a cada 20s (`intervalo_analise_s` do servidor):
  `transcricao_parcial` = últimas 60 falas, `transcricao_nova` = falas
  desde o último envio com sucesso, `historico` = últimas 150. Um envio
  por vez (trava de até 120s). O índice só avança na resposta.
- `POST /audio-transcricao` por pedaço de 15s; o texto volta para a
  extensão, entra em `estado.transcricao` e vai de novo no `/tempo-real`.
- `meeting_id` = código da URL do Meet (`abc-defg-hij`). O áudio da aba
  usa `captaMeetingId`, variável global do service worker.
- Sem autenticação obrigatória nas duas rotas (login é opcional).

**Armazenamento — duas cópias diferentes da mesma reunião**

| Tabela | Escrita por ciclo | Limpeza | Quem lê |
|---|---|---|---|
| `sessoes.transcricao_acumulada` | 1) delta (`main.py:930`), 2) janela de 60 falas (`processador_tempo_real.py:702`, se a IA rodou), 3) janela de 60 falas de novo (`main.py:961`, sempre); + cada trecho de áudio (`main.py:3215`) | nenhuma | tela de Sessões, exportar para o RAG, análise da Conta Claude |
| `meeting_memory.transcript_full` | delta limpo (`_limpar_transcricao`) com `deduplicar_fragmento` | ruído de tela + legenda parcial + repetição | IA (vocabulário do Whisper, recap, diagnóstico), relatórios |

**O que alimenta os agentes:** a janela de 60 falas enviada pela
extensão, limpa e cortada em 6.000 caracteres (`_limitar_contexto_ia`),
mais `historico`, o resumo acumulado e o diagnóstico anterior da
MeetingMemory. Não é a transcrição persistida.

**Síncrono × paralelo:** o `/tempo-real` espera a análise completa
(Coach, DISC, Finance, Closer e Big Five em `asyncio.gather`) antes de
responder — o caminho rápido e o estratégico são o mesmo. Só o Shadow
Mode roda em segundo plano (`create_task`). A transcrição de áudio
(faster-whisper em CPU) e as gravações em `sessoes` (pymysql) rodam
dentro de handlers `async` e travam o event loop do worker.

**Workers:** 2 workers uvicorn; caches em memória por processo
(`_cache_transcricoes`, estado do breaker). MeetingMemory é
ler-modificar-gravar sem lock.

**Provedor ativo:** `TRANSCRICAO_PROVEDOR=whisper_local`, modelo padrão
`small`, CPU, int8 (sem `WHISPER_LOCAL_MODEL` no `.env` de produção).

**Versão da extensão em uso (logs `ext_ver`, 01-11/10):** 1.4.15 em
136.317 linhas de log, 1.4.19 em 2.032 (só 07/10), nenhuma 1.4.20/1.4.21.
As correções A10 (falante) e A12 (só área de legendas) nunca rodaram em
reunião real.

## 2. Números das 63 reuniões (20/09-09/10)

- 99,8% das linhas vêm da legenda do Meet; Whisper em 2 reuniões (56 linhas).
- `sessoes`: **16,9% das linhas são distintas** (83% repetição — janela
  reanexada a cada ciclo); MeetingMemory das mesmas reuniões: 80,1%.
- 78% das linhas rotuladas "João".
- 10 códigos de sala usados em mais de um dia (`mnk-kvoo-pyj`: 36 dias)
  → uma única MeetingMemory acumulando todas as reuniões da sala.

## 3. Matriz de problemas

Gravidade: **A** = distorce o que a IA/vendedor vê ou perde conteúdo;
**M** = degrada; **B** = risco ou custo. Teste = método em
`tests/test_auditoria_transcricao_t01.py` (EF = expectedFailure).

| # | Problema | Arquivo / função | Evidência | Impacto | Correção recomendada | Teste |
|---|---|---|---|---|---|---|
| P1 | Janela de 60 falas reanexada 2x por ciclo em `sessoes` | `main.py:961`, `processador_tempo_real.py:702` → `sessao_manager.salvar_analise` | 16,9% de linhas distintas em produção; 1ª fala aparece 7x em 3 ciclos | **A** — Sessões, RAG e Conta Claude leem texto ~6x repetido | `salvar_analise` grava só a análise; transcrição só pelo delta | `test_cada_fala_aparece_uma_vez_apos_3_ciclos` (EF) |
| P2 | `sessoes` grava o delta sem deduplicar nem limpar | `sessao_manager.salvar_transcricao_bruta` | retry duplica; CSS/aviso entram | **A** | mesma regra da MeetingMemory, ou ler da MeetingMemory | `test_reenvio_do_mesmo_delta_apos_timeout_nao_duplica`, `test_texto_de_tela_nao_e_gravado` (EF) |
| P3 | Fala do áudio gravada 2x em `sessoes` (`[Whisper Local] X` + `Cliente: X`) | `main.py:3215` + `content.js` (`transcricaoAudio` → `/tempo-real`) | leitura de código | **M** | uma única porta de entrada por segmento | `test_mesma_fala_do_audio_e_do_tempo_real_aparece_uma_vez` (EF) |
| P4 | Reunião > 6h para de gravar em `sessoes` (sem erro) | `salvar_transcricao_bruta` (janela `INTERVAL 6 HOUR`, "não recriar aqui") | leitura de código | **B** | sessão por reunião, não por janela de tempo | `test_reuniao_com_mais_de_6h_continua_gravando` (EF) |
| P5 | Sala recorrente = uma MeetingMemory para sempre | `database.registrar_transcricao_meeting` (chave só `meeting_id`) | 10 salas em >1 dia; `transcript_full` de 545 mil caracteres | **A** — contexto, dedup e prompt do Whisper com reuniões de outros dias | identificar a ocorrência da reunião (ex.: `meeting_id` + início da sessão) | `test_sala_recorrente_nao_herda_a_reuniao_de_outro_dia` (EF) |
| P6 | Perda de fragmento com 2 workers (ler-modificar-gravar sem lock) | `registrar_transcricao_meeting` | reproduzido com gravação intercalada | **A** (intermitente) | append transacional / tabela de segmentos com unicidade | `test_dois_workers_ao_mesmo_tempo_nao_perdem_fragmento` (EF) |
| P7 | Objeção repetida legitimamente é descartada (cópia exata em 80 linhas) | `transcript_dedup_rules.eh_duplicata` | reproduzido | **A** — a IA perde a insistência do cliente | dedup por identidade do segmento, não por texto | `test_objecao_repetida_mais_tarde_pelo_cliente_e_mantida` (EF) |
| P8 | Fala parecida de outra pessoa é descartada (similaridade sem olhar falante) | `eh_duplicata` (janela 15, 0,85) | reproduzido | **M** | só comparar fontes diferentes da mesma fala | `test_falas_parecidas_de_pessoas_diferentes_sao_mantidas` (EF) |
| P9 | Fala curta (< 20 caracteres) nunca é deduplicada, nem no reenvio exato | `eh_duplicata` (`min_chars`) | reproduzido | **M** | idempotência por id do segmento | `test_reenvio_exato_de_fala_curta_e_descartado` (EF) |
| P10 | Legenda revisada pelo Meet (começo reescrito) vira duas falas | `compactar_transcricao` (só prefixo) | amostra real 09/10 ("pentear" → "perfil") | **M** | consolidar pela estrutura da legenda (mesmo bloco DOM) na extensão | `test_legenda_revisada_pelo_meet_nao_vira_duas_falas` (EF) |
| P11 | Extensão descarta a versão mais completa de uma legenda já gravada | `content.js::commitarFrase` (`t.startsWith(e.text)` → descarta) | leitura de código | **M** — fim da frase perdido | substituir a versão anterior em vez de descartar a nova | manual (sem ferramenta de teste JS no repo) |
| P12 | Pontuação do Meet impede a junção na extensão ("3:30." × "3:30 a gente") | `commitarFrase` (comparação sem normalizar) | 5,3% das linhas eram legenda parcial | **B** (o backend compacta) | normalizar antes de comparar | controle `test_controle_legenda_crescendo_com_pontuacao_fica_so_a_completa` (backend ok) |
| P13 | Falante errado: 78% "João"; áudio da aba = 1 "Cliente" para todos | `content.js::rotuloParticipante`, `background.js` (`fonte: 'aba'`) | dados de produção; ext 1.4.15 em uso | **A** — objeção/compromisso atribuídos à pessoa errada | instalar ≥1.4.20; depois separar por trilha + diarização (T05) | manual (Meet real) |
| P14 | CSS com rótulo de falante escapa do filtro | `transcript_dedup_rules.eh_ruido_de_tela` (`_CSS_RE` na linha inteira) | "position" 79x como rótulo/linha | **B** | aplicar `_CSS_RE` também ao corpo | `test_css_com_rotulo_de_falante_e_ruido` (EF) |
| P15 | Aviso do Meet "Desativar som do microfone de X" passa como fala | `ruido_interface_rules.eh_texto_de_interface` | amostra real 09/10 | **B** | incluir o prefixo | `test_aviso_de_microfone_de_participante_e_ruido` (EF) |
| P16 | Sem ordem nem idempotência no contrato | `TempoRealRequest`, `AudioTranscricaoRequest` | campos inexistentes | **A** para a T04 (fora de ordem/retry indetectáveis) | `chunk_id`, `sequence`, `start_ms`/`end_ms`, `content_hash` | `test_tempo_real_tem_sequencia...`, `test_audio_tem_sequencia...` (EF) |
| P17 | Transcrição de áudio trava o event loop do worker | `main.py::audio_transcricao` (chamada síncrona em `async def`) | reproduzido (provedor roda dentro do loop) | **A** quando o áudio estiver ligado — para `/tempo-real` de todas as reuniões no worker | `run_in_threadpool`/fila dedicada | `test_transcricao_roda_fora_do_event_loop` (EF) |
| P18 | Áudio não é guardado; buracos entre ciclos de 15s e corte de palavra na fronteira | `offscreen.js`, `content.js::iniciarCicloWhisper`, `main.py` (`os.unlink`) | leitura de código | **A** para Audio-First (sem auditoria/reprocessamento) | T02 (gravação contínua com blocos sequenciados) | manual |
| P19 | Pedaço de microfone < 10 KB descartado (fala curta perdida) | `content.js::iniciarCicloWhisper` | leitura de código | **M** | VAD no servidor em vez de corte por tamanho | manual |
| P20 | `meeting_id` do áudio da aba vem de variável global do service worker | `background.js` (`captaMeetingId`) | MV3 recicla o worker → volta a `'default'` → texto não é gravado (`main.py` ignora `default`) | **M** | `meeting_id` vem no próprio bloco | manual |
| P21 | Texto do áudio é enviado a todas as abas do Meet abertas | `background.js` (`chrome.tabs.query({url: meet})`) | leitura de código | **M** — 2 reuniões abertas misturam texto | enviar só para a aba capturada | manual |
| P22 | Erro HTTP do backend é tratado como sucesso pela extensão | `background.js::fetchBackend` (`ok: true` para qualquer JSON) | leitura de código | **M** — índice avança com o servidor falhando (perda) | repassar o status HTTP | manual |
| P23 | Caminho rápido e estratégico acoplados | `/tempo-real` → `analisar_fragmento_multi` (`gather` de 5 agentes) | leitura de código; atraso ~35-40s medido em 06/10 | **A** para a T06 | separar alerta rápido da análise completa | — (T06) |
| P24 | Rotas de ingestão anônimas aceitam qualquer `meeting_id` | `/tempo-real`, `/audio-transcricao` | leitura de código | **A** (segurança, T11) | autenticação obrigatória + dono da reunião | — (T11) |

**Suspeitas refutadas por teste** (viraram controle):

- legenda + Whisper da mesma fala com números por extenso × algarismos:
  a similaridade junta (`test_controle_legenda_e_whisper_...`);
- reenvio exato de falas longas é descartado na MeetingMemory;
- legenda crescendo com pontuação é compactada no backend;
- linha que é só nome de participante é filtrada no backend.

## 3.1 Status das correções (11/10/2026 — V.1.4.171 + extensão V.1.4.22)

| Status | Problemas | Teste |
|---|---|---|
| **Corrigido** | P1, P2, P3, P4, P5, P6, P7, P8, P9, P10, P14, P15, P17 (backend) | `tests/test_auditoria_transcricao_t01.py` (marcação `expectedFailure` retirada) + `tests/test_transcript_dedup_rules.py` |
| **Corrigido** | P8, P11, P12 (extensão), P19, P20, P21, P22 | `node --test tests/js/test_extensao_transcricao.js` (12 testes; P20-P22 falham contra o `background.js` antigo) |
| Fica para a tarefa do roteiro | P16 (contrato com sequência/idempotência → T02/T04), P18 (gravação do áudio → T02), P23 (caminho rápido → T06), P24 (autenticação na ingestão → T11) | P16 segue `expectedFailure` |
| Depende do usuário + T05 | P13 (falante): instalar a extensão ≥1.4.20 em todos; diarização na T05 | manual |

Como cada correção funciona:

- **P1** `salvar_analise` só grava a análise; a transcrição entra só pelo delta.
- **P2** `salvar_transcricao_bruta` aplica `compactar_transcricao` + `deduplicar_fragmento` (mesmas regras da MeetingMemory).
- **P3** `/audio-transcricao` não grava em `sessoes`; registra o texto em `transcricoes_audio_recentes` (tabela nova).
- **P4** sessão ativa = **atualizada** nas últimas 6h (era criada).
- **P5** MeetingMemory parada há mais de 6h é arquivada (`meeting_id` vira `código#AAAAMMDDhhmm-id`) e a gravação seguinte abre uma nova; o trecho para o Whisper ignora memória parada.
- **P6** gravação com compare-and-swap no tamanho de `transcript_full` + até 5 tentativas.
- **P7** cópia exata só é descartada se estiver colada (≤6 linhas).
- **P8** similaridade só contra texto que o servidor transcreveu do áudio (backend) / só entre legenda e áudio (extensão).
- **P9** reenvio detectado como bloco no fim da base (`linhas_reenviadas`), inclusive fala curta e delta que cresceu.
- **P10** legenda com o começo reescrito pelo Meet: parecida (≥0,8) com o começo da versão seguinte **e** com o fim preservado nela.
- **P11/P12** `chrome-extension/transcricao_rules.js`: versão completa substitui a parcial não enviada; comparação sem pontuação.
- **P14/P15** CSS depois do rótulo do falante; "(Des)ativar som do microfone de X".
- **P17** transcrição e prompt do Whisper em `run_in_threadpool`.
- **P19** corte do pedaço de microfone 10 KB → 4 KB.
- **P20/P21** offscreen manda `meeting_id` e `tabId` em cada pedaço; o texto volta só para a aba capturada.
- **P22** `fetchBackend` devolve `ok` = status 2xx.

## 4. O que depende de validação manual

P11, P13, P18-P22: comportamento da extensão no Meet real (não há
ferramenta de teste JS no repositório; a T02 deve trazer uma). Nada nesta
auditoria foi validado em reunião real.

## 5. Prioridade sugerida antes da T02

1. P1-P2 (sessoes repetida) — barato, afeta o que o usuário lê hoje.
2. Instalar a extensão 1.4.21 (P13, ruído de tela).
3. P5 e P6 (MeetingMemory) — afetam o que a IA recebe.
4. P16-P18 entram no desenho da T02/T04.
