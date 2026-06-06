#!/bin/bash
# SALEIA — Setup VPS (Ubuntu)
# Executa como root: bash setup_vps.sh
set -e

APP_DIR="/opt/saleia"
DOMAIN_API="api.saleia.com.br"
PYTHON="python3"
PIP="pip3"

echo "=== 1. Dependências do sistema ==="
apt-get update -qq
apt-get install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx

echo "=== 2. Criar diretório da aplicação ==="
mkdir -p "$APP_DIR"
rsync -av --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' \
      --exclude='data/*.db' \
      /tmp/saleia_deploy/ "$APP_DIR/"

echo "=== 3. Criar virtual environment ==="
cd "$APP_DIR"
$PYTHON -m venv venv
./venv/bin/pip install --upgrade pip -q
./venv/bin/pip install -r requirements.txt -q
echo "✅ Dependências instaladas"

echo "=== 4. Arquivo .env ==="
if [ ! -f "$APP_DIR/.env" ]; then
    echo "⚠️  Crie o arquivo $APP_DIR/.env com OPENAI_API_KEY e DB_* antes de iniciar."
fi
mkdir -p "$APP_DIR/data/relatorios"

echo "=== 5. Serviço systemd ==="
cat > /etc/systemd/system/saleia.service << 'EOF'
[Unit]
Description=SALEIA FastAPI Backend
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/saleia
EnvironmentFile=/opt/saleia/.env
ExecStart=/opt/saleia/venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable saleia
systemctl restart saleia
echo "✅ Serviço saleia iniciado"

echo "=== 6. Nginx ==="
cat > /etc/nginx/sites-available/saleia << EOF
server {
    listen 80;
    server_name $DOMAIN_API;

    # IPs reais via Cloudflare
    set_real_ip_from 103.21.244.0/22;
    set_real_ip_from 103.22.200.0/22;
    set_real_ip_from 103.31.4.0/22;
    set_real_ip_from 104.16.0.0/13;
    set_real_ip_from 104.24.0.0/14;
    set_real_ip_from 108.162.192.0/18;
    set_real_ip_from 131.0.72.0/22;
    set_real_ip_from 141.101.64.0/18;
    set_real_ip_from 162.158.0.0/15;
    set_real_ip_from 172.64.0.0/13;
    set_real_ip_from 173.245.48.0/20;
    set_real_ip_from 188.114.96.0/20;
    set_real_ip_from 190.93.240.0/20;
    set_real_ip_from 197.234.240.0/22;
    set_real_ip_from 198.41.128.0/17;
    set_real_ip_from 2400:cb00::/32;
    real_ip_header CF-Connecting-IP;

    # CORS para extensão Chrome e dashboard
    add_header Access-Control-Allow-Origin "*" always;
    add_header Access-Control-Allow-Methods "GET, POST, PATCH, DELETE, OPTIONS" always;
    add_header Access-Control-Allow-Headers "Content-Type, Authorization" always;

    location / {
        if (\$request_method = OPTIONS) {
            return 204;
        }
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120;
    }

    # WebSocket (heartbeat)
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_read_timeout 3600;
    }

    # Health check sem log (Cloudflare checa a cada 30s)
    location = /health {
        proxy_pass http://127.0.0.1:8000;
        access_log off;
    }
}
EOF

ln -sf /etc/nginx/sites-available/saleia /etc/nginx/sites-enabled/saleia
nginx -t && systemctl reload nginx
echo "✅ Nginx configurado para $DOMAIN_API"

echo "=== 7. SSL (Let's Encrypt) ==="
certbot --nginx -d "$DOMAIN_API" --non-interactive --agree-tos \
        --email admin@saleia.com.br --redirect || \
    echo "⚠️  Certbot falhou — configure SSL manualmente após o DNS propagar."

echo ""
echo "======================================"
echo " ✅ SALEIA deployado com sucesso!"
echo " API: https://$DOMAIN_API"
echo " Dashboard: https://$DOMAIN_API/dashboard"
echo "======================================"
