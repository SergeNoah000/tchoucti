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


async def send_meeting_reminder_email(
    *,
    to: str,
    member_name: Optional[str],
    association_name: str,
    meeting_title: str,
    meeting_date: str,
    location: Optional[str],
    days_before: int,
    lang: str = "fr",
) -> None:
    """Reminder for an upcoming meeting. `days_before` shapes the salutation.

    Templates are inline / language-keyed (no Jinja). Tone differs slightly
    between the day-of nudge (urgent) and the week-before heads-up (calm).
    """
    greet_name = member_name or ("Bonjour" if lang == "fr" else "Hello")

    if lang == "en":
        if days_before <= 0:
            subject = f"Today: {meeting_title} — {association_name}"
            lead = f"Reminder — today's meeting is <strong>{meeting_title}</strong> at <strong>{meeting_date}</strong>."
        elif days_before == 1:
            subject = f"Tomorrow: {meeting_title} — {association_name}"
            lead = f"See you tomorrow for <strong>{meeting_title}</strong> on <strong>{meeting_date}</strong>."
        else:
            subject = f"In {days_before} days: {meeting_title} — {association_name}"
            lead = f"Heads-up: <strong>{meeting_title}</strong> is scheduled in {days_before} days, on <strong>{meeting_date}</strong>."
        where = f"<p style='margin:0 0 8px;'>📍 {location}</p>" if location else ""
        signoff = "See you there."
    elif lang == "de":
        if days_before <= 0:
            subject = f"Heute: {meeting_title} — {association_name}"
            lead = f"Erinnerung — heute findet <strong>{meeting_title}</strong> am <strong>{meeting_date}</strong> statt."
        elif days_before == 1:
            subject = f"Morgen: {meeting_title} — {association_name}"
            lead = f"Bis morgen zu <strong>{meeting_title}</strong> am <strong>{meeting_date}</strong>."
        else:
            subject = f"In {days_before} Tagen: {meeting_title} — {association_name}"
            lead = f"Hinweis: <strong>{meeting_title}</strong> ist in {days_before} Tagen, am <strong>{meeting_date}</strong>."
        where = f"<p style='margin:0 0 8px;'>📍 {location}</p>" if location else ""
        signoff = "Bis bald."
    else:  # fr (default)
        if days_before <= 0:
            subject = f"Aujourd'hui : {meeting_title} — {association_name}"
            lead = f"Rappel — la séance <strong>{meeting_title}</strong> a lieu aujourd'hui, le <strong>{meeting_date}</strong>."
        elif days_before == 1:
            subject = f"Demain : {meeting_title} — {association_name}"
            lead = f"À demain pour <strong>{meeting_title}</strong>, le <strong>{meeting_date}</strong>."
        else:
            subject = f"Dans {days_before} jours : {meeting_title} — {association_name}"
            lead = f"Pour information, <strong>{meeting_title}</strong> est prévue dans {days_before} jours, le <strong>{meeting_date}</strong>."
        where = f"<p style='margin:0 0 8px;'>📍 {location}</p>" if location else ""
        signoff = "À très vite."

    text_body = (
        f"{greet_name},\n\n"
        f"{meeting_title} — {association_name}\n"
        f"{meeting_date}\n"
        + (f"Lieu : {location}\n" if location else "")
        + f"\n{signoff}\n"
    )
    html_body = _wrap_html(f"""
      <p style="margin:0 0 12px;font-size:18px;font-weight:600;">{greet_name},</p>
      <p style="margin:0 0 12px;">{lead}</p>
      {where}
      <p style="margin:16px 0 0;color:#64748b;">— {association_name}</p>
    """)

    await send_email(to=to, subject=subject, text_body=text_body, html_body=html_body)


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


async def send_account_created_email(
    *,
    to: str,
    invitee_name: Optional[str],
    association_name: Optional[str],
    login_url: str,
    has_default_password: bool,
) -> None:
    """Mail de bienvenue « votre compte a été créé » — SANS le mot de passe.

    Envoyé en plus (et séparément) du mail d'activation. Si le compte a un mot
    de passe par défaut, on invite à se connecter et à le changer ; sinon on
    renvoie vers le mail d'activation.
    """
    greet = f"Bonjour {invitee_name}," if invitee_name else "Bonjour,"
    scope = f" au sein de <strong>{association_name}</strong>" if association_name else ""
    subject = f"Votre compte Tchoucti a été créé — {association_name or 'plateforme'}"

    if has_default_password:
        cta_text = (
            "Un mot de passe vous a été communiqué par votre administrateur. "
            "Connectez-vous puis changez-le dès la première connexion."
        )
    else:
        cta_text = (
            "Vous allez recevoir un e-mail séparé contenant le lien d'activation "
            "de votre compte pour définir votre mot de passe."
        )

    text_body = (
        f"{greet}\n\n"
        f"Votre compte a été créé sur la plateforme Tchoucti"
        f"{' au sein de ' + association_name if association_name else ''}.\n\n"
        f"{cta_text}\n\n"
        f"Connexion : {login_url}\n"
    )

    html_body = _wrap_html(f"""
      <p style="margin:0 0 12px;font-size:18px;font-weight:600;">{greet}</p>
      <p style="margin:0 0 16px;">Votre compte a été créé sur la plateforme <strong>Tchoucti</strong>{scope}.</p>
      <p style="margin:0 0 24px;">{cta_text}</p>
      <p style="margin:0 0 24px;text-align:center;">
        <a href="{login_url}" style="display:inline-block;background:#0d9488;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:600;">Se connecter</a>
      </p>
    """)

    await send_email(to=to, subject=subject, text_body=text_body, html_body=html_body)


async def send_meeting_recap_email(
    *,
    to: str,
    member_name: Optional[str],
    association_name: str,
    meeting_title: str,
    meeting_date: str,
    presents: int,
    absents: int,
    excused: int,
    total_collected: str,
    agenda: Optional[str],
    notes: Optional[str],
    report_url: Optional[str],
) -> None:
    """Récap envoyé à chaque membre à la clôture d'une séance."""
    greet = f"Bonjour {member_name}," if member_name else "Bonjour,"
    subject = f"Récap — {meeting_title} ({association_name})"

    agenda_block = f"Ordre du jour : {agenda}\n" if agenda else ""
    notes_excerpt = ""
    if notes:
        excerpt = notes if len(notes) <= 600 else notes[:600].rstrip() + "…"
        notes_excerpt = f"\nCompte-rendu :\n{excerpt}\n"
    report_line = (
        f"\nProcès-verbal complet : {report_url}\n" if report_url else ""
    )

    text_body = (
        f"{greet}\n\n"
        f"La séance « {meeting_title} » du {meeting_date} vient d'être clôturée.\n\n"
        f"Présents : {presents}  |  Excusés : {excused}  |  Absents : {absents}\n"
        f"Total encaissé : {total_collected}\n\n"
        f"{agenda_block}"
        f"{notes_excerpt}"
        f"{report_line}"
        f"\n— {association_name}\n"
    )

    agenda_html = (
        f"<p style='margin:0 0 8px;'><strong>Ordre du jour :</strong> {agenda}</p>"
        if agenda else ""
    )
    notes_html = ""
    if notes:
        excerpt_html = (notes if len(notes) <= 600 else notes[:600].rstrip() + "…").replace("\n", "<br/>")
        notes_html = (
            "<p style='margin:16px 0 4px;font-weight:600;'>Compte-rendu</p>"
            f"<p style='margin:0 0 12px;color:#334155;'>{excerpt_html}</p>"
        )
    report_html = (
        f"<p style='margin:16px 0 0;text-align:center;'>"
        f"<a href='{report_url}' style='display:inline-block;background:#0d9488;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:600;'>Télécharger le PV complet</a>"
        f"</p>" if report_url else ""
    )

    html_body = _wrap_html(
        f"<p style='margin:0 0 12px;font-size:18px;font-weight:600;'>{greet}</p>"
        f"<p style='margin:0 0 16px;'>La séance <strong>{meeting_title}</strong> du <strong>{meeting_date}</strong> vient d'être clôturée.</p>"
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='border-collapse:separate;border-spacing:8px 0;margin:0 0 12px;'>"
        f"<tr>"
        f"<td style='background:#ecfdf5;border-radius:8px;padding:10px;'><div style='font-size:11px;color:#065f46;text-transform:uppercase;letter-spacing:0.05em;'>Présents</div><div style='font-size:20px;font-weight:700;color:#065f46;'>{presents}</div></td>"
        f"<td style='background:#eff6ff;border-radius:8px;padding:10px;'><div style='font-size:11px;color:#1e40af;text-transform:uppercase;letter-spacing:0.05em;'>Excusés</div><div style='font-size:20px;font-weight:700;color:#1e40af;'>{excused}</div></td>"
        f"<td style='background:#fef2f2;border-radius:8px;padding:10px;'><div style='font-size:11px;color:#991b1b;text-transform:uppercase;letter-spacing:0.05em;'>Absents</div><div style='font-size:20px;font-weight:700;color:#991b1b;'>{absents}</div></td>"
        "</tr></table>"
        f"<p style='margin:0 0 16px;font-size:15px;'><strong>Total encaissé :</strong> {total_collected}</p>"
        f"{agenda_html}"
        f"{notes_html}"
        f"{report_html}"
        f"<p style='margin:24px 0 0;color:#64748b;'>— {association_name}</p>"
    )

    await send_email(to=to, subject=subject, text_body=text_body, html_body=html_body)
