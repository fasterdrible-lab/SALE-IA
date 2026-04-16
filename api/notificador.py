"""
Módulo de Notificação do SALEIA.

Envia o relatório da reunião automaticamente ao vendedor via:
- WhatsApp (Z-API)
- E-mail (SMTP / Gmail)

Se WhatsApp falhar, tenta e-mail automaticamente (fallback).
Se ambos falharem, loga o erro mas não quebra o sistema.
"""

import json
import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import quote

import httpx

# Configuração de logging
logger = logging.getLogger(__name__)


def _formatar_mensagem_whatsapp(relatorio: dict) -> str:
    """
    Formata o relatório como mensagem clara para WhatsApp.
    Usa o template de mensagem definido em prompt_templates.
    """
    # Extrai dados do relatório com valores padrão seguros
    data = relatorio.get("data", "N/A")
    nome_cliente = relatorio.get("nome_cliente", "Cliente")

    # Dados do produto recomendado
    produto_info = relatorio.get("produto_recomendado", {})
    produto = produto_info.get("nome", "N/A")
    valor = produto_info.get("valor", "N/A")
    justificativa = produto_info.get("justificativa", "N/A")

    # Perfil DISC
    disc_info = relatorio.get("perfil_comportamental", {})
    perfil = disc_info.get("perfil_disc", "N/A")
    como_abordar = disc_info.get("como_abordar", "N/A")

    # Objeções
    objecoes = relatorio.get("top_objecoes", [])
    objecao_1 = objecoes[0] if len(objecoes) > 0 else {}
    objecao_2 = objecoes[1] if len(objecoes) > 1 else {}
    objecao_3 = objecoes[2] if len(objecoes) > 2 else {}

    # Sinal oculto
    sinal_oculto = relatorio.get("sinal_oculto", "N/A")

    # Próximos passos
    passos = relatorio.get("proximos_passos", ["N/A", "N/A", "N/A"])
    passo_1 = passos[0] if len(passos) > 0 else "N/A"
    passo_2 = passos[1] if len(passos) > 1 else "N/A"
    passo_3 = passos[2] if len(passos) > 2 else "N/A"

    # ID do relatório para link
    relatorio_id = relatorio.get("relatorio_id", "")
    base_url = os.getenv("BASE_URL", "https://seuservidor.com")
    link_relatorio = f"{base_url}/relatorio/{quote(relatorio_id, safe='')}" if relatorio_id else ""

    mensagem = f"""🤖 *SALEIA — Relatório da Reunião*
📅 {data} | 👤 {nome_cliente}

━━━━━━━━━━━━━━━━━━━━
💰 *PRODUTO RECOMENDADO*
{produto} — {valor}
_{justificativa}_

━━━━━━━━━━━━━━━━━━━━
🎯 *PERFIL DISC*
{perfil} — {como_abordar}

━━━━━━━━━━━━━━━━━━━━
⚠️ *TOP OBJEÇÕES ESPERADAS*
1. {objecao_1.get('objecao', 'N/A')} → {objecao_1.get('resposta_sugerida', 'N/A')}
2. {objecao_2.get('objecao', 'N/A')} → {objecao_2.get('resposta_sugerida', 'N/A')}
3. {objecao_3.get('objecao', 'N/A')} → {objecao_3.get('resposta_sugerida', 'N/A')}

━━━━━━━━━━━━━━━━━━━━
⚡ *O QUE VOCÊ NÃO PERCEBEU*
{sinal_oculto}

━━━━━━━━━━━━━━━━━━━━
✅ *PRÓXIMOS PASSOS*
1. {passo_1}
2. {passo_2}
3. {passo_3}"""

    if link_relatorio:
        mensagem += f"\n\n_Ver relatório completo: {link_relatorio}_"

    return mensagem


def _formatar_email_html(relatorio: dict) -> str:
    """
    Formata o relatório como e-mail HTML bem estruturado.
    """
    nome_cliente = relatorio.get("nome_cliente", "Cliente")
    data = relatorio.get("data", "N/A")

    # Converte o relatório em HTML legível
    conteudo_json = json.dumps(relatorio, ensure_ascii=False, indent=2)

    produto_info = relatorio.get("produto_recomendado", {})
    disc_info = relatorio.get("perfil_comportamental", {})
    resumo = relatorio.get("resumo_executivo", "")

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 700px; margin: 0 auto; padding: 20px;">
        <h1 style="color: #2563eb;">🤖 SALEIA — Relatório da Reunião</h1>
        <p style="color: #6b7280;">📅 {data} | 👤 {nome_cliente}</p>

        <hr style="border-color: #e5e7eb;">

        <h2 style="color: #1f2937;">📋 Resumo Executivo</h2>
        <p style="background: #f3f4f6; padding: 15px; border-radius: 8px;">{resumo}</p>

        <h2 style="color: #1f2937;">💰 Produto Recomendado</h2>
        <p><strong>{produto_info.get('nome', 'N/A')}</strong> — {produto_info.get('valor', 'N/A')}</p>
        <p><em>{produto_info.get('justificativa', 'N/A')}</em></p>

        <h2 style="color: #1f2937;">🎯 Perfil DISC</h2>
        <p><strong>{disc_info.get('perfil_disc', 'N/A')}</strong></p>
        <p>{disc_info.get('como_abordar', 'N/A')}</p>

        <h2 style="color: #1f2937;">⚡ Sinal Oculto</h2>
        <p style="background: #fef3c7; padding: 15px; border-radius: 8px; border-left: 4px solid #f59e0b;">
            {relatorio.get('sinal_oculto', 'N/A')}
        </p>

        <h2 style="color: #1f2937;">⚠️ Top Objeções</h2>
        <ul>
        {''.join(f"<li><strong>{o.get('objecao', '')}</strong> → {o.get('resposta_sugerida', '')}</li>" for o in relatorio.get('top_objecoes', []))}
        </ul>

        <h2 style="color: #1f2937;">✅ Próximos Passos</h2>
        <ol>
        {''.join(f"<li>{p}</li>" for p in relatorio.get('proximos_passos', []))}
        </ol>

        <hr style="border-color: #e5e7eb;">
        <p style="color: #9ca3af; font-size: 12px;">
            Gerado automaticamente pelo SALEIA — Sistema de Automação de Leads
        </p>
    </body>
    </html>
    """
    return html


async def enviar_whatsapp(relatorio: dict) -> bool:
    """
    Envia o relatório via WhatsApp usando a Z-API.

    Args:
        relatorio: Dicionário com os dados do relatório.

    Returns:
        True se enviado com sucesso, False caso contrário.
    """
    zapi_instance = os.getenv("ZAPI_INSTANCE")
    zapi_token = os.getenv("ZAPI_TOKEN")
    zapi_phone = os.getenv("ZAPI_PHONE")

    if not all([zapi_instance, zapi_token, zapi_phone]):
        logger.warning("⚠️ Z-API não configurada. Pulando envio WhatsApp.")
        return False

    url = f"https://api.z-api.io/instances/{zapi_instance}/token/{zapi_token}/send-text"
    mensagem = _formatar_mensagem_whatsapp(relatorio)

    payload = {
        "phone": zapi_phone,
        "message": mensagem,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resposta = await client.post(url, json=payload)
            resposta.raise_for_status()
            logger.info(f"✅ WhatsApp enviado com sucesso para {zapi_phone}")
            return True
    except httpx.HTTPStatusError as e:
        logger.error(f"❌ Erro HTTP ao enviar WhatsApp: {e.response.status_code} — {e.response.text}")
        return False
    except Exception as e:
        logger.error(f"❌ Erro ao enviar WhatsApp: {e}")
        return False


async def enviar_email(relatorio: dict) -> bool:
    """
    Envia o relatório por e-mail via SMTP.

    Args:
        relatorio: Dicionário com os dados do relatório.

    Returns:
        True se enviado com sucesso, False caso contrário.
    """
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    email_vendedor = os.getenv("EMAIL_VENDEDOR")

    if not all([smtp_user, smtp_pass, email_vendedor]):
        logger.warning("⚠️ SMTP não configurado. Pulando envio de e-mail.")
        return False

    nome_cliente = relatorio.get("nome_cliente", "Cliente")
    data = relatorio.get("data", "N/A")
    assunto = f"🤖 SALEIA — Relatório da Reunião com {nome_cliente} ({data})"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = assunto
    msg["From"] = smtp_user
    msg["To"] = email_vendedor

    # Versão texto simples (fallback)
    texto_simples = _formatar_mensagem_whatsapp(relatorio)
    parte_texto = MIMEText(texto_simples, "plain", "utf-8")
    parte_html = MIMEText(_formatar_email_html(relatorio), "html", "utf-8")

    msg.attach(parte_texto)
    msg.attach(parte_html)

    try:
        # Cria contexto SSL com verificação de certificado (previne ataques MITM)
        contexto_ssl = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port) as servidor:
            servidor.ehlo()
            servidor.starttls(context=contexto_ssl)
            servidor.login(smtp_user, smtp_pass)
            servidor.sendmail(smtp_user, email_vendedor, msg.as_string())
        logger.info(f"✅ E-mail enviado com sucesso para {email_vendedor}")
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error("❌ Erro de autenticação SMTP. Verifique usuário e senha.")
        return False
    except Exception as e:
        logger.error(f"❌ Erro ao enviar e-mail: {e}")
        return False


async def notificar_vendedor(relatorio: dict) -> dict:
    """
    Envia o relatório ao vendedor via WhatsApp (com fallback para e-mail).

    Estratégia de envio:
    1. Tenta WhatsApp via Z-API
    2. Se falhar, tenta e-mail via SMTP
    3. Se ambos falharem, loga o erro mas não quebra o sistema

    Args:
        relatorio: Dicionário com os dados completos do relatório.

    Returns:
        Dicionário com status de cada canal de envio.
    """
    resultado = {
        "whatsapp": False,
        "email": False,
        "canal_utilizado": None,
        "erro": None,
    }

    # Tenta WhatsApp primeiro
    whatsapp_ok = await enviar_whatsapp(relatorio)
    resultado["whatsapp"] = whatsapp_ok

    if whatsapp_ok:
        resultado["canal_utilizado"] = "whatsapp"
        logger.info("📱 Relatório enviado via WhatsApp")
        return resultado

    # Fallback: tenta e-mail
    logger.info("📧 WhatsApp falhou, tentando e-mail como fallback...")
    email_ok = await enviar_email(relatorio)
    resultado["email"] = email_ok

    if email_ok:
        resultado["canal_utilizado"] = "email"
        logger.info("📧 Relatório enviado via e-mail (fallback)")
        return resultado

    # Ambos falharam — loga mas não quebra o sistema
    mensagem_erro = "❌ Falha ao enviar notificação por WhatsApp e e-mail. Verifique as configurações."
    logger.error(mensagem_erro)
    resultado["erro"] = mensagem_erro

    return resultado
