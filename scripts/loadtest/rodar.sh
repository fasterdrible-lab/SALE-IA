#!/bin/bash
# SALEIA — D7 (teste de carga, seção 32 do PROMPT MESTRE V2).
# Rodar na VPS como root, de madrugada: bash /opt/saleia/scripts/loadtest/rodar.sh
#
# Monta uma instância de TESTE isolada da produção e desmonta no fim:
#   - código: cópia do HEAD de /opt/saleia em /opt/saleia-loadtest (data/ próprio)
#   - banco: saleia_loadtest (só base_conhecimento copiada, para o RAG ter o que buscar)
#   - IA: scripts/loadtest/fake_ai.py na porta 8099 (nunca provedor real; sem chaves)
#   - app: uvicorn na porta 8010, 2 workers (igual à produção); sem Telegram/OTel/SMTP
# Só começa com reunioes_ativas = 0 na produção, e o gerador para sozinho se
# uma reunião real começar. Relatório em /root/loadtest/.
set -euo pipefail

PROD=/opt/saleia
LT=/opt/saleia-loadtest
DB_LT=saleia_loadtest
SAIDA_DIR=/root/loadtest
CARIMBO=$(date -u +%Y%m%d_%H%M)
NIVEIS=${NIVEIS:-10,50,100}
MINUTOS=${MINUTOS:-5}
mkdir -p "$SAIDA_DIR"
exec > >(tee -a "$SAIDA_DIR/d7_$CARIMBO.log") 2>&1

ativas=$(curl -s http://127.0.0.1:8000/health | python3 -c "import sys,json; print(json.load(sys.stdin).get('reunioes_ativas'))")
if [ "$ativas" != "0" ]; then
    echo "[$(date -u +%T)] produção com reunioes_ativas=$ativas — teste NÃO executado"
    exit 0
fi

desmontar() {
    echo "[$(date -u +%T)] desmontando"
    journalctl -u saleia-lt-app --no-pager -o cat -p warning > "$SAIDA_DIR/d7_${CARIMBO}_app_avisos.txt" 2>/dev/null || true
    systemctl stop saleia-lt-app saleia-lt-fakeai 2>/dev/null || true
    mysql -e "DROP DATABASE IF EXISTS $DB_LT" || true
    rm -rf "$LT"
}
trap desmontar EXIT

echo "[$(date -u +%T)] montando $LT a partir de $(git -C "$PROD" log --oneline -1)"
rm -rf "$LT" && mkdir -p "$LT"
git -C "$PROD" archive HEAD | tar -x -C "$LT"

# .env de teste: sem nenhuma chave real nem canal externo.
grep -v -E '^(OPENAI_API_KEY|ANTHROPIC_API_KEY|GEMINI_API_KEY|GOOGLE_API_KEY|DEEPSEEK_API_KEY|DEEPSEEK_BASE_URL|GROQ_API_KEY|TELEGRAM_[A-Z_]*|OTEL_[A-Z_]*|SMTP_[A-Z_]*|EMAIL_FROM|DB_NAME|CLAUDE_[A-Z_]*|KNOWLEDGE_COMPILER_ENABLED|GRAVACAO_AUDIO_ENABLED|PROVEDOR_PREFERIDO|AI_PROVIDER_ORDER|LANGFUSE_[A-Z_]*|OBSERVABILITY_ENABLED|APP_BASE_URL)=' \
    "$PROD/.env" > "$LT/.env"
cat >> "$LT/.env" <<'EOF'
DB_NAME=saleia_loadtest
DEEPSEEK_API_KEY=loadtest-fake
DEEPSEEK_BASE_URL=http://127.0.0.1:8099
AI_PROVIDER_ORDER=deepseek
PROVEDOR_PREFERIDO=deepseek
CLAUDE_ACCOUNT_PILOT=false
KNOWLEDGE_COMPILER_ENABLED=false
GRAVACAO_AUDIO_ENABLED=false
OBSERVABILITY_ENABLED=false
TELEGRAM_TOKEN=
EOF
chmod 600 "$LT/.env"

DB_USER=$(grep -E '^DB_USER=' "$PROD/.env" | cut -d= -f2- | tr -d "\"'")
HOST_USER=$(mysql -N -e "SELECT host FROM mysql.user WHERE user='$DB_USER' ORDER BY host='localhost' DESC LIMIT 1")
mysql -e "DROP DATABASE IF EXISTS $DB_LT; CREATE DATABASE $DB_LT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; GRANT ALL ON $DB_LT.* TO '$DB_USER'@'$HOST_USER'"
mysqldump saleia base_conhecimento | mysql "$DB_LT"

systemd-run --quiet --unit=saleia-lt-fakeai -p WorkingDirectory="$LT" \
    "$PROD/venv/bin/python" -m uvicorn scripts.loadtest.fake_ai:app --host 127.0.0.1 --port 8099 --log-level warning
systemd-run --quiet --unit=saleia-lt-app -p WorkingDirectory="$LT" \
    "$PROD/venv/bin/python" -m uvicorn api.main:app --host 127.0.0.1 --port 8010 --workers 2 --timeout-graceful-shutdown 25 --log-level warning

for i in $(seq 60); do
    curl -sf http://127.0.0.1:8010/health >/dev/null && break
    sleep 2
done
curl -s http://127.0.0.1:8010/health | python3 -c "import sys,json; d=json.load(sys.stdin); print('instância de teste:', d.get('versao'), d.get('status'))"

cd "$LT"
"$PROD/venv/bin/python" -m scripts.loadtest.gerar_carga --niveis "$NIVEIS" --minutos "$MINUTOS" \
    --saida "$SAIDA_DIR/d7_$CARIMBO.json"
echo "[$(date -u +%T)] relatório: $SAIDA_DIR/d7_$CARIMBO.json"
