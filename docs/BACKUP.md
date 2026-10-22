# SALEIA — Backup e restauração

> Criado em 13/10/2026. Antes disso não havia backup automático: o único
> dump era o manual de 11/10/2026 (`/root/backups/saleia_pre_reset_*.sql.gz`).

## O que roda

`saleia-backup.timer` → `saleia-backup.service` →
`deploy/systemd/saleia-backup.sh`, todo dia às **05:30 UTC (02:30 BRT)**,
antes do reinício diário das 06:00 UTC. Instalado por
`bash deploy/systemd/instalar.sh` (não reinicia o `saleia`).

| O quê | Como | Onde | Guarda |
|---|---|---|---|
| MySQL `saleia` | `mysqldump --single-transaction` (não trava InnoDB, pode rodar com reunião), gzip, conferido (`gzip -t` + ≥ 40 `CREATE TABLE`) | `/root/backups/saleia/mysql/saleia_AAAAMMDD_HHMM.sql.gz` | 14 dias |
| `/opt/saleia/data/` (gravações, arquivos da Base e da Biblioteca, `metricas.db`, `ai_provider_order.json`…) | `rsync --link-dest`: arquivo igual ao do dia anterior vira hardlink e não ocupa espaço de novo | `/root/backups/saleia/data/AAAAMMDD_HHMM/` | 7 snapshots |

Prioridade baixa de CPU e disco (`nice 19`, `ionice idle`). Pasta com
permissão só do root (`700`, dumps `600`). Falha → mensagem no Telegram
("backup diário falhou") e o serviço termina com erro.

O `.env` **não** entra no backup (segredos). Guarde uma cópia dele fora
da VPS por conta própria (gerenciador de senhas).

## Cópia fora da VPS — Backblaze B2 (desde 21/10/2026)

No fim do backup diário, `deploy/systemd/saleia-backup-externo.sh` envia
para o bucket B2 **`SALEIA`** (privado, criptografado SSE-B2, conta
`fasterdrible`), via rclone (remote `b2saleia`,
`/root/.config/rclone/rclone.conf`, `600`):

| O quê | Onde no bucket | Como |
|---|---|---|
| cada dump novo do MySQL | `mysql/saleia_AAAAMMDD_HHMM.sql.gz` | lista local dos enviados (`/root/backups/saleia/b2_estado/mysql_enviados`) |
| `data/` **sem `gravacoes/`** | `data/<mesmo caminho>` | só o que mudou desde o último envio bom (marcador `b2_estado/data_marcador`); 1º envio = tudo |

As gravações (990 MB, ~38 mil pedaços, retenção de 7 dias) ficam só nos
snapshots locais: `SALEIA_B2_GRAVACOES=1` no ambiente do serviço as inclui.
Arquivo apagado entre a listagem e o envio não conta como falha.

- Arquivo reenviado com o mesmo nome vira nova versão; a regra de
  lifecycle do bucket apaga versões antigas/escondidas após **30 dias**.
  Os dumps no B2 não são apagados pelo script (cerca de 50 MB/dia).
- A chave deve ser **Write Only** e restrita ao bucket: a VPS envia, mas
  não lê nem apaga — quem invadir a VPS não destrói o backup externo.
- Falha → Telegram ("backup externo (B2) falhou") e o `saleia-backup`
  termina com erro. Sem `rclone.conf`, a etapa é pulada.
- Reenviar `data/` inteiro: `rm /root/backups/saleia/b2_estado/data_marcador`.

**Restaurar do B2** (VPS perdida): na conta Backblaze, criar uma chave
**Read Only** do bucket `SALEIA` (a da VPS não lê), configurar o rclone
na máquina nova e baixar:

```bash
rclone copy b2saleia:SALEIA/mysql/<dump>.sql.gz /root/restauro/
rclone copy b2saleia:SALEIA/data /opt/saleia/data
```

Depois seguir "Restaurar" abaixo. O `.env` não está no B2 (segredos).

## Conferir

```bash
systemctl list-timers 'saleia-*' --no-pager
journalctl -u saleia-backup --since '-2 days' --no-pager
ls -lh /root/backups/saleia/mysql/ | tail -3
ls -1 /root/backups/saleia/data/
du -sh /root/backups/saleia
# rodar agora (seguro a qualquer hora):
systemctl start saleia-backup && journalctl -u saleia-backup -n 20 --no-pager
```

## Restaurar

Sempre com `reunioes_ativas: 0` no `/health` e o serviço parado.

**Banco inteiro**

```bash
systemctl stop saleia
# guarda o estado atual antes de sobrescrever
mysqldump -u root --single-transaction saleia | gzip > /root/backups/antes_restauracao_$(date -u +%Y%m%d_%H%M).sql.gz
zcat /root/backups/saleia/mysql/saleia_AAAAMMDD_HHMM.sql.gz | mysql -u root saleia
systemctl start saleia
curl -s http://127.0.0.1:8000/health
```

**Só para consultar (sem mexer em produção)**: restaurar num banco à
parte (`mysql -u root -e 'CREATE DATABASE saleia_restauro'` e
`zcat ... | mysql -u root saleia_restauro`), consultar e apagar depois
(`DROP DATABASE saleia_restauro`).

**Arquivos de `data/`**

```bash
# um arquivo ou pasta (ex.: uma gravação apagada por engano)
cp -a /root/backups/saleia/data/AAAAMMDD_HHMM/gravacoes/<reunião>/ /opt/saleia/data/gravacoes/
# tudo (com o serviço parado)
systemctl stop saleia
rsync -a --delete /root/backups/saleia/data/AAAAMMDD_HHMM/ /opt/saleia/data/
systemctl start saleia
```

Gravações e banco andam juntos: restaurar só um deles deixa
`gravacoes_blocos` apontando para arquivos que não existem (ou o
contrário). Para voltar no tempo, use o dump e o snapshot do mesmo dia.

## Espaço

1º backup (13/10/2026 20:47 UTC, rodado à mão na instalação): dump do
MySQL **3,8 MB** (46 tabelas, conferido), snapshot de `data/` **26 MB**
(gravações idênticas às de produção), total 30 MB, em ~1s. `data/` cresce com as
gravações (~60-70 MB por hora de reunião com as 2 trilhas; retenção de
90 dias); os snapshots só ocupam o que mudou. Disco em 13/10/2026: 150 GB,
117 GB livres. A mensagem do backup informa uso total e disco livre.
