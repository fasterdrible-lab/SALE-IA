"""Envio de e-mail via SMTP para recuperação de senha."""
import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)


def enviar_email_recuperacao(email_destino: str, token: str) -> bool:
    """
    Envia e-mail com link de redefinição de senha.
    Retorna True se enviado com sucesso, False caso contrário.
    Requer no .env: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM (opcional).
    """
    smtp_host = os.environ.get("SMTP_HOST", "")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    email_from = os.environ.get("EMAIL_FROM") or smtp_user
    base_url = os.environ.get("APP_BASE_URL", "https://api.saleia.com.br")

    if not all([smtp_host, smtp_user, smtp_pass]):
        logger.warning("[Email] SMTP não configurado — variáveis SMTP_HOST/SMTP_USER/SMTP_PASS ausentes.")
        return False

    link = f"{base_url}/reset?token={token}"
    corpo_html = f"""<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;background:#0f172a;color:#e2e8f0;padding:32px;margin:0">
  <div style="max-width:480px;margin:0 auto;background:#1e293b;border-radius:12px;padding:32px">
    <h2 style="color:#38bdf8;margin-top:0">Recuperação de Senha — SALEIA</h2>
    <p>Recebemos uma solicitação para redefinir a senha da sua conta.</p>
    <p>Clique no botão abaixo para criar uma nova senha.<br>
       O link expira em <strong>1 hora</strong>.</p>
    <a href="{link}"
       style="display:inline-block;background:#38bdf8;color:#0f172a;padding:12px 24px;
              border-radius:8px;text-decoration:none;font-weight:bold;margin:16px 0">
      Redefinir minha senha
    </a>
    <p style="font-size:12px;color:#94a3b8;margin-top:24px">
      Se você não solicitou a recuperação, ignore este e-mail.<br>
      Link direto: {link}
    </p>
  </div>
</body>
</html>"""

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Recuperação de senha — SALEIA"
        msg["From"] = email_from
        msg["To"] = email_destino
        msg.attach(MIMEText(corpo_html, "html", "utf-8"))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(smtp_user, smtp_pass)
            smtp.sendmail(email_from, [email_destino], msg.as_string())

        logger.info("[Email] E-mail de recuperação enviado para %s", email_destino)
        return True
    except Exception as e:
        logger.error("[Email] Falha ao enviar e-mail de recuperação: %s", e)
        return False
