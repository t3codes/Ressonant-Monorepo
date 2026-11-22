from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.config.settings import Settings

logger = logging.getLogger(__name__)


def build_invite_url(frontend_base_url: str, token: str) -> str:
    base = frontend_base_url.rstrip("/")
    return f"{base}/#/convite?token={token}"


def _escape(value: str | None) -> str:
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def send_invitation_email(
    *,
    settings: Settings,
    to_email: str,
    invite_url: str,
    workspace_name: str | None = None,
    organization_name: str | None = None,
    inviter_name: str | None = None,
    role: str | None = None,
    expires_at: str | None = None,
) -> bool:
    if not settings.email_enabled or not settings.smtp_host:
        return False

    subject = "Convite para o Ressonant"
    location = workspace_name or organization_name or "um espaço no Ressonant"
    invited_by = inviter_name or "Um administrador"
    role_label = {"admin": "Administrador", "member": "Membro"}.get(role or "", role or "Membro")
    expires_label = expires_at or "7 dias"
    text = (
        f"{invited_by} convidou você para acessar {location} no Ressonant.\n\n"
        f"Papel: {role_label}\n"
        f"Expira em: {expires_label}\n\n"
        f"Aceite o convite pelo link:\n{invite_url}\n\n"
        "Se você ainda não tem conta, crie sua conta com este mesmo e-mail e depois confirme o convite.\n"
    )
    html = f"""\
<html>
  <body style="margin:0;padding:24px;background:#f4f7f8;font-family:Arial,sans-serif;color:#1f2937">
    <div style="max-width:560px;margin:0 auto;background:#ffffff;border:1px solid #dbe5e7;border-radius:16px;padding:24px">
      <h1 style="margin:0 0 12px;font-size:24px;color:#0f172a">Convite para o Ressonant</h1>
      <p style="margin:0 0 12px"><strong>{_escape(invited_by)}</strong> convidou você para acessar <strong>{_escape(location)}</strong>.</p>
      <p style="margin:0 0 8px"><strong>Organização:</strong> {_escape(organization_name or "-")}</p>
      <p style="margin:0 0 8px"><strong>Workspace:</strong> {_escape(workspace_name or "-")}</p>
      <p style="margin:0 0 8px"><strong>Papel:</strong> {_escape(role_label)}</p>
      <p style="margin:0 0 20px"><strong>Expira em:</strong> {_escape(expires_label)}</p>
      <p style="margin:0 0 20px"><a href="{invite_url}" style="display:inline-block;padding:12px 18px;background:#46C2BF;color:#062a2a;text-decoration:none;border-radius:10px;font-weight:700">Aceitar convite</a></p>
      <p style="margin:0 0 8px;color:#475569;font-size:14px">Se o botão não funcionar, copie e cole este link no navegador:</p>
      <p style="margin:0 0 20px;font-size:14px;word-break:break-all"><a href="{invite_url}" style="color:#0f766e">{invite_url}</a></p>
      <p style="margin:0;color:#6b7280;font-size:13px">Se você ainda não tem conta, crie sua conta com este mesmo e-mail e depois confirme o convite.</p>
    </div>
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
