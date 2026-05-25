@echo off
chcp 65001 >nul
title SALEIA — Backend IA

echo.
echo  =============================================
echo   SALEIA — Sistema de Vendas com IA
echo  =============================================
echo.

cd /d "%~dp0"

:: Verificar se o venv existe
if not exist "venv\Scripts\activate.bat" (
    echo [1/3] Criando ambiente virtual Python...
    python -m venv venv
    if errorlevel 1 (
        echo ERRO: Python nao encontrado. Instale Python 3.11+
        pause
        exit /b 1
    )
)

:: Ativar venv
echo [2/3] Ativando ambiente virtual...
call venv\Scripts\activate.bat

:: Instalar dependencias se necessario
echo [3/3] Verificando dependencias...
pip install -q -r requirements.txt

echo.
echo  Backend iniciado em: http://localhost:8000
echo  Documentacao API:    http://localhost:8000/docs
echo  Ultimo relatorio:    http://localhost:8000/relatorio
echo  Lista relatorios:    http://localhost:8000/relatorios
echo.
echo  Pressione Ctrl+C para parar.
echo.

uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

pause
