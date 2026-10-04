#!/bin/bash
# SALEIA — instala as units do systemd versionadas em deploy/systemd/ (D12).
# Rodar na VPS como root, depois do git pull: bash deploy/systemd/instalar.sh
# NÃO reinicia o saleia: a unit nova (ExecStart/RuntimeMaxSec) vale no
# próximo reinício, que o próprio timer faz às 03:00 BRT sem reunião ativa.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

cp /etc/systemd/system/saleia.service "/etc/systemd/system/saleia.service.bak_$(date +%Y%m%d%H%M%S)"
install -m 644 "$DIR/saleia.service" /etc/systemd/system/saleia.service
install -m 644 "$DIR/saleia-restart-diario.service" /etc/systemd/system/saleia-restart-diario.service
install -m 644 "$DIR/saleia-restart-diario.timer" /etc/systemd/system/saleia-restart-diario.timer
chmod +x "$DIR/saleia-restart-diario.sh"

systemd-analyze verify /etc/systemd/system/saleia.service \
    /etc/systemd/system/saleia-restart-diario.service \
    /etc/systemd/system/saleia-restart-diario.timer
systemctl daemon-reload
systemctl enable --now saleia-restart-diario.timer
systemctl list-timers saleia-restart-diario.timer --no-pager
