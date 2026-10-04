#!/bin/bash
# SALEIA — reinício diário seguro (D12, V.1.4.163).
# Chamado por saleia-restart-diario.timer às 06:00 UTC (03:00 BRT).
# Só reinicia com reunioes_ativas = 0 (mesmo sinal do deploy); com reunião
# ativa, espera e tenta de novo a cada 5 min por até 3h.

HEALTH_URL="http://127.0.0.1:8000/health"
INTERVALO=300
TENTATIVAS=36
UPTIME_MINIMO=$((12 * 3600))

uptime_servico() {
    local inicio
    inicio=$(systemctl show saleia -p ActiveEnterTimestamp --value)
    [ -z "$inicio" ] && { echo 0; return; }
    echo $(( $(date +%s) - $(date -d "$inicio" +%s) ))
}

reunioes_ativas() {
    curl -fsS --max-time 15 "$HEALTH_URL" \
        | /usr/bin/python3 -c 'import json,sys; print(int(json.load(sys.stdin).get("reunioes_ativas") or 0))' \
        2>/dev/null
}

if ! systemctl is-active --quiet saleia; then
    echo "saleia nao esta ativo; nada a fazer (Restart=always cuida da subida)."
    exit 0
fi

UP=$(uptime_servico)
if [ "$UP" -lt "$UPTIME_MINIMO" ]; then
    echo "saleia subiu ha $((UP / 3600))h (< 12h, ex.: deploy recente); reinicio de hoje pulado."
    exit 0
fi

for i in $(seq 1 "$TENTATIVAS"); do
    ATIVAS=$(reunioes_ativas)
    if [ "$ATIVAS" = "0" ]; then
        echo "tentativa $i: reunioes_ativas=0, reiniciando saleia."
        systemctl restart saleia
        sleep 10
        if systemctl is-active --quiet saleia; then
            echo "saleia ativo apos o reinicio."
            exit 0
        fi
        echo "ERRO: saleia nao voltou ativo apos o reinicio."
        exit 1
    fi
    echo "tentativa $i: reunioes_ativas=${ATIVAS:-?} (health indisponivel ou reuniao em curso), nova tentativa em $((INTERVALO / 60)) min."
    sleep "$INTERVALO"
done

echo "reinicio de hoje desistido apos 3h com reuniao ativa/health indisponivel; RuntimeMaxSec=48h segue como rede de seguranca."
exit 0
