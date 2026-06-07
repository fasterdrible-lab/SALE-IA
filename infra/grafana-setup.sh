#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
# SALEIA — Instalação rápida do Grafana Alloy na VPS
# Executar como root: bash grafana-setup.sh
# ──────────────────────────────────────────────────────────────────────────────

set -e

echo "==> Adicionando repositório Grafana..."
apt-get install -y apt-transport-https software-properties-common wget
mkdir -p /etc/apt/keyrings
wget -q -O /etc/apt/keyrings/grafana.gpg https://apt.grafana.com/gpg.key
echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" \
  | tee /etc/apt/sources.list.d/grafana.list

echo "==> Instalando Grafana Alloy..."
apt-get update -qq
apt-get install -y alloy

echo "==> Copiando config..."
cp /opt/saleia/infra/grafana-alloy.alloy /etc/alloy/config.alloy

echo ""
echo "⚠️  ATENÇÃO: Edite /etc/alloy/config.alloy e substitua:"
echo "    GRAFANA_CLOUD_URL      → URL do Prometheus remote write"
echo "    GRAFANA_CLOUD_USER     → User ID numérico"
echo "    GRAFANA_CLOUD_API_KEY  → API Key"
echo ""
echo "Depois:"
echo "    systemctl enable alloy"
echo "    systemctl start alloy"
echo "    systemctl status alloy"
echo ""
echo "✅ Grafana Alloy instalado. Configure as credenciais e inicie o serviço."
