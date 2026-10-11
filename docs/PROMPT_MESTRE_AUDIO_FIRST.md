# Prompt Mestre — Audio-First (recebido em 11/10/2026)

Roteiro de 12 tarefas sequenciais passado pelo usuário em 11/10/2026.
Cada tarefa só começa depois da anterior validada (testes passando,
pendências manuais registradas como bloqueio).

| # | Tarefa | Estado |
|---|---|---|
| T01 | Auditoria da arquitetura atual | **feita 11/10** — `docs/AUDITORIA_TRANSCRICAO_T01.md`, `tests/test_auditoria_transcricao_t01.py` |
| T02 | Gravação contínua do áudio (aba + microfone em trilhas separadas, blocos com `meeting_id`/`track_id`/`chunk_id`/`sequence`/`start_ms`/`end_ms`/`codec`/`sample_rate`/`content_hash`/`recorded_at`; consentimento e indicador visível) | **código + testes automáticos feitos 11/10** (V.1.4.172 + ext 1.4.23, desligada por padrão); **bloqueio: validação manual no Meet real** — em andamento desde 11/10 19:43 UTC (flag ligada na VPS): blocos sem lacuna, integridade ok, pausa/retomada ok; trilha da aba chegou em silêncio (a confirmar se havia outro participante falando); faltam 30 min com 2 pessoas, sobreposição e queda de conexão |
| T03 | Pipeline de transcrição incremental (faster-whisper, janelas 5/10/15s, VAD, segmentos com timestamps, provisório × confirmado, `condition_on_previous_text=False` avaliado, WER/CER/latência/CPU medidos) | não iniciada |
| T04 | Consolidação e deduplicação (idempotência por segmento, unicidade no banco, fora de ordem, 2 workers, repetição legítima preservada) | não iniciada |
| T05 | Identificação dos participantes (trilha mic × aba, diarização avaliada, rótulos provisórios, confiança, DER) | não iniciada |
| T06 | Motor de inteligência comercial rápida (12 eventos prioritários; meta ≤5s alerta, ≤10s orientação; p50/p95) | não iniciada |
| T07 | Integração com os agentes Coach/DISC/Finance/Closer/Big Five (camada estratégica não bloqueia a rápida) | não iniciada |
| T08 | Nova experiência do vendedor (indicadores de captura, alertas, área estratégica, controles) | não iniciada |
| T09 | Transcrição definitiva pós-reunião (literal auditável + revisada) | não iniciada |
| T10 | Auditoria das decisões (evidência, timestamp, áudio, fato × hipótese) | não iniciada |
| T11 | Segurança, privacidade e retenção | não iniciada |
| T12 | Benchmark e validação final (qualidade, desempenho, carga) | não iniciada |

Regras do roteiro que valem para todas as tarefas: não refatorar a
aplicação inteira; reutilizar agentes/banco/logs existentes; feature flag
com padrão seguro e rollback; testes automatizados obrigatórios; nunca
usar resposta de IA como prova de áudio/captura/diarização/latência;
documentar o que foi testado automaticamente e o que depende de reunião
real; legendas do Meet nunca misturadas automaticamente com a transcrição
de áudio; captura de áudio nunca ativada automaticamente após atualização;
nada direto em produção (dev → homologação → produção com flag).

Ao fim de cada tarefa: tabela Tarefa / Implementação / Arquivos / Testes /
Segurança / Desempenho / Pendências / Status.
