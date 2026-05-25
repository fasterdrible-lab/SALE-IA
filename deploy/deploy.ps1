# SALEIA — Deploy para VPS
# Executa no PowerShell: .\deploy\deploy.ps1

$VPS = "204.168.180.25"
$VPS_USER = "root"
$LOCAL = "C:\Users\phpos\OneDrive\SALE-IA\SALEIA"

Write-Host "=== SALEIA Deploy ===" -ForegroundColor Cyan

# 1. Empacotar (exclui venv, cache, db local)
Write-Host "1. Empacotando..." -ForegroundColor Yellow
$tmp = "$env:TEMP\saleia_deploy.tar.gz"
Set-Location $LOCAL

tar -czf $tmp `
    --exclude="./venv" `
    --exclude="./__pycache__" `
    --exclude="./*.pyc" `
    --exclude="./data/*.db" `
    --exclude="./data/relatorios/*.json" `
    --exclude="./.env" `
    .

Write-Host "   Pacote: $tmp" -ForegroundColor Gray

# 2. Enviar para VPS
Write-Host "2. Enviando para VPS..." -ForegroundColor Yellow
scp $tmp "${VPS_USER}@${VPS}:/tmp/saleia_deploy.tar.gz"

# 3. Extrair e rodar setup no VPS
Write-Host "3. Configurando VPS..." -ForegroundColor Yellow
$cmds = @"
set -e
mkdir -p /tmp/saleia_deploy
tar -xzf /tmp/saleia_deploy.tar.gz -C /tmp/saleia_deploy
bash /tmp/saleia_deploy/deploy/setup_vps.sh
"@

ssh "${VPS_USER}@${VPS}" $cmds

Write-Host ""
Write-Host "=====================================" -ForegroundColor Green
Write-Host " Deploy concluido!" -ForegroundColor Green
Write-Host " API:       https://api.saleia.com.br" -ForegroundColor Green
Write-Host " Dashboard: https://api.saleia.com.br/dashboard" -ForegroundColor Green
Write-Host "=====================================" -ForegroundColor Green
