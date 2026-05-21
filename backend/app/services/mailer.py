"""Email sending — stdlib smtplib wrapped in asyncio.to_thread.

In dev the container points to Mailpit (no TLS, no auth). In prod set SMTP_*
env vars to a real provider. Email failures are logged and re-raised so the
caller can decide whether to surface them to the user (e.g. allow the admin to
copy the invitation link manually if SMTP is down).
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage
from typing import Iterable, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class MailError(Exception):
    """Raised when sending fails. The caller can choose to swallow or surface."""


def _send_sync(msg: EmailMessage) -> None:
    """Blocking SMTP send — call via asyncio.to_thread."""
    host, port = settings.SMTP_HOST, settings.SMTP_PORT
    use_tls = bool(settings.SMTP_TLS)
    user = settings.SMTP_USER or None
    password = settings.SMTP_PASSWORD or None

    try:
        if use_tls and port == 465:
            client = smtplib.SMTP_SSL(host, port, timeout=10)
        else:
            client = smtplib.SMTP(host, port, timeout=10)
            if use_tls:
                client.starttls()
        with client:
            if user and password:
                client.login(user, password)
            client.send_message(msg)
    except Exception as exc:  # noqa: BLE001 — re-raised as MailError
        logger.exception("SMTP send failed via %s:%s", host, port)
        raise MailError(str(exc)) from exc


async def send_email(
    *,
    to: str | Iterable[str],
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
    reply_to: Optional[str] = None,
) -> None:
    """Send a multipart email asynchronously."""
    recipients = [to] if isinstance(to, str) else list(to)
    if not recipients:
        raise MailError("No recipient given")

    msg = EmailMessage()
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    await asyncio.to_thread(_send_sync, msg)


# ─────────────────────────────────────────────────────────────────────────
# Templates — kept inline (no Jinja). One function per email kind.
# ─────────────────────────────────────────────────────────────────────────
def _wrap_html(body_html: str) -> str:
    """Minimal HTML wrapper with brand-ish styling. Inline CSS only."""
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f4f4f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;color:#0f172a;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:32px 16px;">
    <tr><td align="center">
      <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e4e4e7;">
        <tr><td style="padding:32px 32px 0;">
          <div style="display:inline-block;padding:8px 12px;border-radius:8px;background:#0d9488;color:#fff;font-weight:700;letter-spacing:-0.01em;">Tchoucti</div>
        </td></tr>
        <tr><td style="padding:24px 32px 32px;line-height:1.55;font-size:15px;">
          {body_html}
        </td></tr>
        <tr><td style="padding:16px 32px;background:#f8fafc;color:#64748b;font-size:12px;text-align:center;">
          Tchoucti — Plateforme des associations
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


async def send_invitation_email(
    *,
    to: str,
    invitee_name: Optional[str],
    activation_url: str,
    inviter_name: Optional[str],
    groupement_name: Optional[str],
    role_label: str,
    message: Optional[str] = None,
    expires_in_days: int = 7,
) -> None:
    greet = f"Bonjour {invitee_name}," if invitee_name else "Bonjour,"
    by = f" par {inviter_name}" if inviter_name else ""
    scope = f" pour rejoindre <strong>{groupement_name}</strong>" if groupement_name else ""

    subject = f"Invitation à rejoindre Tchoucti — {groupement_name or 'plateforme'}"

    text_body = (
        f"{greet}\n\n"
        f"Vous avez été invité·e{by}{' pour rejoindre ' + groupement_name if groupement_name else ''}"
        f" en tant que {role_label} sur la plateforme Tchoucti.\n\n"
        f"Activez votre compte en cliquant sur le lien suivant :\n{activation_url}\n\n"
        f"Ce lien expire dans {expires_in_days} jours.\n"
    )
    if message:
        text_body += f"\nMessage de l'invitant :\n{message}\n"
    text_body += "\nSi vous n'attendiez pas cette invitation, vous pouvez ignorer cet e-mail."

    extra = f'<p style="margin:16px 0 0;padding:12px 14px;background:#f1f5f9;border-radius:8px;color:#334155;"><em>“{message}”</em></p>' if message else ""

    html_body = _wrap_html(f"""
      <p style="margin:0 0 12px;font-size:18px;font-weight:600;">{greet}</p>
      <p style="margin:0 0 16px;">Vous avez été invité·e{by}{scope} en tant que <strong>{role_label}</strong> sur la plateforme Tchoucti.</p>
      <p style="margin:0 0 24px;">Cliquez sur le bouton ci-dessous pour activer votre compte&nbsp;:</p>
      <p style="margin:0 0 24px;text-align:center;">
        <a href="{activation_url}" style="display:inline-block;background:#0d9488;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:600;">Activer mon compte</a>
      </p>
      <p style="margin:0 0 8px;font-size:13px;color:#64748b;">Ou copiez ce lien dans votre navigateur&nbsp;:</p>
      <p style="margin:0;font-family:Menlo,Monaco,monospace;font-size:12px;color:#475569;word-break:break-all;">{activation_url}</p>
      <p style="margin:24px 0 0;font-size:13px;color:#64748b;">Ce lien expire dans <strong>{expires_in_days} jours</strong>.</p>
      {extra}
    """)

    await send_email(to=to, subject=subject, text_body=text_body, html_body=html_body)
