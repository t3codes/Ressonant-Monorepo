from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.config.settings import Settings

logger = logging.getLogger(__name__)


def build_invite_url(frontend_base_url: str, token: str) -> str:
    base = frontend_base_url.rstrip("/")
    return f"{base}/#/convite?token={token}"


def send_invitation_email(
    *,
    settings: Settings,
    to_email: str,
    invite_url: str,
    workspace_name: str | None = None,
    organization_name: str | None = None,
) -> bool:
    if not settings.email_enabled or not settings.smtp_host:
        return False

    subject = "Convite para o Ressonant"
    location = workspace_name or organization_name or "um espaço no Ressonant"
    text = (
        f"Você foi convidado para acessar {location} no Ressonant.\n\n"
        f"Aceite o convite pelo link:\n{invite_url}\n\n"
        "Se você ainda não tem conta, crie sua conta com este mesmo e-mail e depois confirme o convite.\n"
    )
    html = f"""\
<html>
  <body style="font-family:Arial,sans-serif;line-height:1.5;color:#1f2937">
    <p>Você foi convidado para acessar <strong>{location}</strong> no Ressonant.</p>
    <p><a href="{invite_url}" style="display:inline-block;padding:10px 16px;background:#46C2BF;color:#062a2a;text-decoration:none;border-radius:8px;font-weight:600">Aceitar convite</a></p>
    <p>Se o botão não funcionar, copie e cole este link no navegador:</p>
    <p><a href="{invite_url}">{invite_url}</a></p>
    <p style="color:#6b7280;font-size:13px">Se você ainda não tem conta, crie sua conta com este mesmo e-mail e depois confirme o convite.</p>
  </body>
</html>
"""

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = to_email
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    try:
        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
                if settings.smtp_username:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
                smtp.ehlo()
                if settings.smtp_use_tls:
                    smtp.starttls()
                    smtp.ehlo()
                if settings.smtp_username:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(msg)
        return True
    except Exception:
        logger.exception("Falha ao enviar e-mail de convite para %s", to_email)
        return False
