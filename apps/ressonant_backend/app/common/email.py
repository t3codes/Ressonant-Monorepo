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
    corporate_email: str | None = None,
) -> bool:
    if not settings.email_enabled or not settings.smtp_host:
        return False

    subject = "Convite para o Ressonant"
    location = workspace_name or organization_name or "um espaço no Ressonant"
    invited_by = inviter_name or "Um administrador"
    role_label = {"admin": "Administrador", "member": "Membro"}.get(role or "", role or "Membro")
    expires_label = expires_at or "7 dias"
    corporate_line = (
        f"E-mail corporativo de login (somente leitura): {corporate_email}"
        if corporate_email
        else ""
    )
    text = (
        f"{invited_by} convidou você para acessar {location} no Ressonant.\n\n"
        f"Papel: {role_label}\n"
        f"Expira em: {expires_label}\n\n"
        + (f"{corporate_line}\n\n" if corporate_line else "")
        + f"Aceite o convite pelo link:\n{invite_url}\n\n"
        + (
            "Ao aceitar, sua conta será criada com o e-mail corporativo informado acima; "
            "este endereço é apenas o contato que recebeu o convite.\n"
            if corporate_email
            else "Ao aceitar, você informará seus dados e criará sua conta no Ressonant.\n"
        )
    )
    corporate_html = (
        '<p style="margin:0 0 8px"><strong>E-mail corporativo de login (somente leitura):</strong> '
        f"{_escape(corporate_email)}</p>"
        if corporate_email
        else ""
    )
    accept_note = (
        "Ao aceitar, sua conta será criada com o e-mail corporativo informado acima; "
        "este endereço é apenas o contato que recebeu o convite."
        if corporate_email
        else "Ao aceitar, você informará seus dados e criará sua conta no Ressonant."
    )
    html = (
        "<html>"
        '<body style="margin:0;padding:24px;background:#f4f7f8;'
        'font-family:Arial,sans-serif;color:#1f2937">'
        '<div style="max-width:560px;margin:0 auto;background:#ffffff;'
        'border:1px solid #dbe5e7;border-radius:16px;padding:24px">'
        '<h1 style="margin:0 0 12px;font-size:24px;color:#0f172a">'
        "Convite para o Ressonant</h1>"
        f'<p style="margin:0 0 12px"><strong>{_escape(invited_by)}</strong> '
        f"convidou você para acessar <strong>{_escape(location)}</strong>.</p>"
        f'<p style="margin:0 0 8px"><strong>Organização:</strong> '
        f"{_escape(organization_name or '-')}</p>"
        f'<p style="margin:0 0 8px"><strong>Workspace:</strong> '
        f"{_escape(workspace_name or '-')}</p>"
        f'<p style="margin:0 0 8px"><strong>Papel:</strong> {_escape(role_label)}</p>'
        f'<p style="margin:0 0 8px"><strong>Expira em:</strong> '
        f"{_escape(expires_label)}</p>"
        f"{corporate_html}"
        f'<p style="margin:0 0 20px"><a href="{invite_url}" '
        'style="display:inline-block;padding:12px 18px;background:#46C2BF;'
        'color:#062a2a;text-decoration:none;border-radius:10px;font-weight:700">'
        "Aceitar convite</a></p>"
        '<p style="margin:0 0 8px;color:#475569;font-size:14px">'
        "Se o botão não funcionar, copie e cole este link no navegador:</p>"
        f'<p style="margin:0 0 20px;font-size:14px;word-break:break-all">'
        f'<a href="{invite_url}" style="color:#0f766e">{invite_url}</a></p>'
        f'<p style="margin:0;color:#6b7280;font-size:13px">'
        f"{_escape(accept_note)}</p>"
        "</div></body></html>"
    )

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
        # Destinatário, token e credenciais não entram em log (AGENTS.md §5).
        logger.exception("Falha ao enviar e-mail de convite")
        return False
