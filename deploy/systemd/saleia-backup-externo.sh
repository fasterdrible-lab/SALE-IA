#!/bin/bash
# SALEIA — cópia do backup diário para fora da VPS (Backblaze B2, bucket
# SALEIA, remote rclone "b2saleia" em /root/.config/rclone/rclone.conf).
# Chamado no fim de saleia-backup.sh (21/10/2026, migração de VPS).
#
# A chave do B2 é Write Only: não lista nem apaga. Por isso o envio é
# incremental pelo estado local, sem consultar o bucket:
#   - mysql/: cada dump novo (lista dos já enviados em $ESTADO/mysql_enviados)
#   - data/: arquivos de /opt/saleia/data alterados desde o último envio bom
#     (marcador $ESTADO/data_marcador). 1º envio = data/ inteiro.
#     Sem gravacoes/ (990 MB, ~38 mil pedaços, retenção de 7 dias na VPS;
#     ficam só nos snapshots locais) — SALEIA_B2_GRAVACOES=1 inclui.
# Arquivo reenviado com o mesmo nome vira nova versão no B2; versões
# antigas e apagadas somem sozinhas em 30 dias (lifecycle do bucket).
# Restauração: docs/BACKUP.md.
#
# --retries 1: sem listar o bucket (chave Write Only), cada nova tentativa
# do rclone reenviaria a lista inteira (21/10: o 1º envio estourou as 2h do
# serviço assim). A rede já é retentada por arquivo (--low-level-retries).

set -uo pipefail

REMOTO="${SALEIA_B2_REMOTO:-b2saleia:SALEIA}"
RAIZ="${SALEIA_BACKUP_DIR:-/root/backups/saleia}"
APP="/opt/saleia"
ESTADO="$RAIZ/b2_estado"
RCLONE=(nice -n 19 ionice -c3 rclone --no-check-dest --transfers 4 --retries 1 --low-level-retries 10 --stats-one-line --stats 0)
EXCLUIR=(-path ./gravacoes -prune -o)
[ "${SALEIA_B2_GRAVACOES:-0}" = "1" ] && EXCLUIR=()

mkdir -p "$ESTADO"
chmod 700 "$ESTADO"

avisar_falha() {
    local motivo="$1"
    echo "ERRO: $motivo"
    local token chat
    token=$(grep -E '^TELEGRAM_TOKEN=' "$APP/.env" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")
    chat=$(grep -E '^TELEGRAM_CHAT_ID=' "$APP/.env" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")
    if [ -n "$token" ] && [ -n "$chat" ]; then
        curl -4 -fsS --max-time 15 "https://api.telegram.org/bot${token}/sendMessage" \
            --data-urlencode "chat_id=${chat}" \
            --data-urlencode "text=⚠️ SALEIA: backup externo (B2) falhou — ${motivo}" >/dev/null 2>&1 || true
    fi
}

FALHAS=0

# ── 1. Dumps do MySQL ainda não enviados ─────────────────────────────────
touch "$ESTADO/mysql_enviados"
ENVIADOS=0
for f in "$RAIZ"/mysql/*.sql.gz; do
    [ -e "$f" ] || continue
    nome=$(basename "$f")
    grep -qxF "$nome" "$ESTADO/mysql_enviados" && continue
    if "${RCLONE[@]}" copyto "$f" "$REMOTO/mysql/$nome"; then
        echo "$nome" >> "$ESTADO/mysql_enviados"
        ENVIADOS=$((ENVIADOS + 1))
    else
        avisar_falha "envio do dump $nome"
        FALHAS=$((FALHAS + 1))
    fi
done
echo "b2 mysql: $ENVIADOS dump(s) enviado(s)"

# ── 2. data/ alterado desde o último envio bom ──────────────────────────
NOVO_MARCADOR="$ESTADO/data_marcador.novo"
touch "$NOVO_MARCADOR"   # antes do find: o que mudar durante o envio vai no próximo
LISTA="$ESTADO/data_lista.txt"
NOVOS=()
[ -e "$ESTADO/data_marcador" ] && NOVOS=(-newer "$ESTADO/data_marcador")
(cd "$APP/data" && find . "${EXCLUIR[@]}" -type f "${NOVOS[@]}" ! -name '*.tmp' ! -name '.*.tmp' -printf '%P\n') > "$LISTA"
QTD=$(wc -l < "$LISTA")
LOG_RCLONE="$ESTADO/rclone_data.log"
if [ "$QTD" -eq 0 ]; then
    mv "$NOVO_MARCADOR" "$ESTADO/data_marcador"
    echo "b2 data: nada novo"
elif "${RCLONE[@]}" copy --files-from-raw "$LISTA" "$APP/data" "$REMOTO/data" > "$LOG_RCLONE" 2>&1 \
        || ! grep 'ERROR' "$LOG_RCLONE" | grep -vqE 'no such file or directory|Attempt [0-9]+/[0-9]+ failed'; then
    # Arquivo apagado entre a listagem e o envio (gravação em pedaços,
    # retenção) não é falha: some do data/ de propósito.
    mv "$NOVO_MARCADOR" "$ESTADO/data_marcador"
    echo "b2 data: $QTD arquivo(s) na lista, $(grep -c 'no such file or directory' "$LOG_RCLONE") sumiram antes do envio"
else
    tail -5 "$LOG_RCLONE"
    rm -f "$NOVO_MARCADOR"   # marcador antigo fica: o próximo envio repete tudo
    avisar_falha "envio de data/ ($QTD arquivos)"
    FALHAS=$((FALHAS + 1))
fi

[ "$FALHAS" -eq 0 ] || exit 1
exit 0
