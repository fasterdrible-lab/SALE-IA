#!/bin/bash
# SALEIA — backup diário (13/10/2026, infra sem versão nova do backend). Chamado por saleia-backup.timer às
# 05:30 UTC (02:30 BRT), antes do reinício diário das 06:00 UTC.
#
# 1. MySQL: mysqldump --single-transaction (não trava as tabelas InnoDB,
#    não atrapalha reunião em curso), gzip, conferido; guarda 14 dias.
# 2. data/ (gravações, arquivos da Base/Biblioteca, métricas): snapshot
#    com rsync --link-dest — arquivo que não mudou vira hardlink do
#    snapshot anterior e não ocupa espaço de novo; guarda 7 dias.
#
# Fica no mesmo disco da VPS: protege contra erro de aplicação, apagamento
# e reset por engano, NÃO contra perda da VPS. Cópia para fora: ver
# docs/BACKUP.md. Falha avisa no Telegram (sem segredo na mensagem).
# Restauração: docs/BACKUP.md.

set -uo pipefail

RAIZ="${SALEIA_BACKUP_DIR:-/root/backups/saleia}"
APP="/opt/saleia"
DB="${SALEIA_BACKUP_DB:-saleia}"
DIAS_MYSQL=14
DIAS_DATA=7
MIN_TABELAS=40
AGORA="$(date -u +%Y%m%d_%H%M)"

mkdir -p "$RAIZ/mysql" "$RAIZ/data"
chmod 700 "$RAIZ"

avisar_falha() {
    local motivo="$1"
    echo "ERRO: $motivo"
    local token chat
    token=$(grep -E '^TELEGRAM_TOKEN=' "$APP/.env" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")
    chat=$(grep -E '^TELEGRAM_CHAT_ID=' "$APP/.env" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")
    if [ -n "$token" ] && [ -n "$chat" ]; then
        curl -4 -fsS --max-time 15 "https://api.telegram.org/bot${token}/sendMessage" \
            --data-urlencode "chat_id=${chat}" \
            --data-urlencode "text=⚠️ SALEIA: backup diário falhou — ${motivo}" >/dev/null 2>&1 || true
    fi
}

FALHAS=0

# ── 1. MySQL ──────────────────────────────────────────────────────────────
DUMP="$RAIZ/mysql/${DB}_${AGORA}.sql.gz"
TMP="$DUMP.parcial"
if nice -n 19 ionice -c3 mysqldump -u root --single-transaction --quick --routines --triggers \
        --default-character-set=utf8mb4 "$DB" | gzip -6 > "$TMP"; then
    TABELAS=$(zcat "$TMP" | grep -c '^CREATE TABLE' || true)
    if gzip -t "$TMP" && [ "${TABELAS:-0}" -ge "$MIN_TABELAS" ]; then
        mv "$TMP" "$DUMP"
        chmod 600 "$DUMP"
        echo "mysql ok: $(basename "$DUMP") $(du -h "$DUMP" | cut -f1), $TABELAS tabelas"
    else
        rm -f "$TMP"
        avisar_falha "dump do MySQL incompleto ($TABELAS tabelas, mínimo $MIN_TABELAS)"
        FALHAS=$((FALHAS + 1))
    fi
else
    rm -f "$TMP"
    avisar_falha "mysqldump terminou com erro"
    FALHAS=$((FALHAS + 1))
fi
# Só apaga os antigos se houver pelo menos um dump bom recente.
if ls "$RAIZ"/mysql/*.sql.gz >/dev/null 2>&1; then
    find "$RAIZ/mysql" -name '*.sql.gz' -mtime +"$DIAS_MYSQL" -delete
fi

# ── 2. data/ ──────────────────────────────────────────────────────────────
ULTIMO=$(ls -1d "$RAIZ"/data/20*[0-9] 2>/dev/null | tail -1)
DESTINO="$RAIZ/data/$AGORA"
LINK=()
[ -n "$ULTIMO" ] && LINK=(--link-dest="$ULTIMO")
if nice -n 19 ionice -c3 rsync -a --delete "${LINK[@]}" \
        --exclude '*.tmp' --exclude '.*.tmp' "$APP/data/" "$DESTINO.parcial/"; then
    mv "$DESTINO.parcial" "$DESTINO"
    chmod 700 "$DESTINO"
    echo "data ok: $(basename "$DESTINO") $(du -sh "$DESTINO" | cut -f1) (espaço novo de fato menor: hardlinks)"
    # Mantém os DIAS_DATA snapshots mais recentes.
    ls -1d "$RAIZ"/data/20*[0-9] 2>/dev/null | head -n -"$DIAS_DATA" | xargs -r rm -rf
else
    rm -rf "$DESTINO.parcial"
    avisar_falha "cópia de data/ (rsync) terminou com erro"
    FALHAS=$((FALHAS + 1))
fi

echo "uso total do backup: $(du -sh "$RAIZ" | cut -f1); disco livre: $(df -h / | awk 'NR==2{print $4}')"

# ── 3. Cópia para fora da VPS (B2) ───────────────────────────────────────
# Só se o remote estiver configurado; a falha já avisa no Telegram lá dentro.
if [ -f /root/.config/rclone/rclone.conf ]; then
    bash "$APP/deploy/systemd/saleia-backup-externo.sh" || FALHAS=$((FALHAS + 1))
fi

[ "$FALHAS" -eq 0 ] || exit 1
exit 0
