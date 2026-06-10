"""Service de notifications — crée des lignes Notification (in-app) et,
optionnellement, envoie un email. Best-effort : ne lève jamais (les flux métier
ne doivent pas échouer à cause d'une notif).
"""
from __future__ import annotations

import logging
from typing import Iterable, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationKind
from app.models.role import (
    MembershipRole,
    MembershipStatus,
    Membership,
    Role,
)
from app.models.user import User
from app.services.mailer import MailError, send_email

logger = logging.getLogger(__name__)


async def bureau_users_of(db: AsyncSession, association_id: UUID) -> list[User]:
    """Utilisateurs du bureau (rôle != 'member') d'une association, ACTIFS.
    Sert à notifier les décideurs (demandes de prêt / aide à traiter)."""
    res = await db.execute(
        select(User)
        .distinct()
        .join(Membership, Membership.user_id == User.id)
        .join(MembershipRole, MembershipRole.membership_id == Membership.id)
        .join(Role, Role.id == MembershipRole.role_id)
        .where(
            Membership.association_id == association_id,
            Membership.status == MembershipStatus.ACTIVE,
            Role.code != "member",
            User.is_active.is_(True),
        )
    )
    return list(res.scalars().all())


async def notify_user(
    db: AsyncSession,
    *,
    user: User,
    kind: NotificationKind,
    title: str,
    body: Optional[str] = None,
    action_url: Optional[str] = None,
    association_id: Optional[UUID] = None,
    data: Optional[dict] = None,
    send_mail: bool = False,
    commit: bool = False,
) -> Optional[Notification]:
    """Crée une notification in-app pour `user` (+ email si `send_mail`).

    Le caller commit (ou passe commit=True). Email best-effort.
    """
    try:
        notif = Notification(
            user_id=user.id,
            association_id=association_id,
            kind=kind,
            title=title,
            body=body,
            action_url=action_url,
            data=data or {},
        )
        db.add(notif)
        if commit:
            await db.commit()
            await db.refresh(notif)
        else:
            await db.flush()
    except Exception:  # pragma: no cover — ne bloque jamais le flux métier.
        logger.exception("Échec de création de notification in-app pour %s", user.id)
        notif = None

    if send_mail and user.email and user.is_active:
        try:
            html = (
                f"<p style='margin:0 0 12px;font-size:18px;font-weight:600;'>Bonjour {user.full_name},</p>"
                f"<p style='margin:0 0 16px;'>{body or title}</p>"
                + (
                    f"<p style='margin:16px 0 0;text-align:center;'><a href='{action_url}' "
                    "style='display:inline-block;background:#0d9488;color:#fff;padding:10px 18px;"
                    "border-radius:8px;text-decoration:none;font-weight:600;'>Voir dans l'application</a></p>"
                    if action_url else ""
                )
            )
            from app.services.mailer import _wrap_html

            await send_email(
                to=user.email,
                subject=title,
                text_body=f"Bonjour {user.full_name},\n\n{body or title}\n"
                + (f"\n{action_url}\n" if action_url else ""),
                html_body=_wrap_html(html),
            )
        except MailError:
            pass
        except Exception:  # pragma: no cover
            logger.exception("Échec d'envoi d'email de notification à %s", user.email)

    return notif


async def notify_users(
    db: AsyncSession,
    *,
    users: Iterable[User],
    kind: NotificationKind,
    title: str,
    body: Optional[str] = None,
    action_url: Optional[str] = None,
    association_id: Optional[UUID] = None,
    data: Optional[dict] = None,
    send_mail: bool = False,
) -> None:
    """Notifie plusieurs utilisateurs (in-app + email optionnel). Le caller commit."""
    for u in users:
        await notify_user(
            db,
            user=u,
            kind=kind,
            title=title,
            body=body,
            action_url=action_url,
            association_id=association_id,
            data=data,
            send_mail=send_mail,
            commit=False,
        )
