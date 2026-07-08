"""Importer de MEMBRES.

Crée directement le User (sans email d'invitation) + la Membership + les rôles.
Un membre « papier » sans email reçoit un email placeholder unique (modifiable
plus tard) car ``User.email`` est obligatoire et unique globalement.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import get_password_hash
from app.models.association import Association
from app.models.invitation import (
    Invitation,
    InvitationKind,
    InvitationStatus,
    generate_invitation_token,
)
from app.models.role import (
    MemberCategory,
    Membership,
    MembershipRole,
    MembershipStatus,
    Role,
)
from app.models.user import User, UserType
from app.services.mailer import (
    MailError,
    send_account_created_email,
    send_invitation_email,
)

from .base import Choice, ImportColumn, Importer

_ADMIN_ROLE_CODES = {"association_admin", "association_manager"}


def hash_token(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def _activation_url(plain_token: str) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/activate?token={plain_token}"


def _login_url() -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/login"

_STATUS = (
    Choice("active", "Actif"),
    Choice("suspended", "Suspendu"),
    Choice("resigned", "Démissionnaire"),
)
_CATEGORY = (
    Choice("active", "Actif"),
    Choice("honorary", "Honoraire"),
    Choice("founder", "Fondateur"),
    Choice("suspended", "Suspendu"),
)
_VALID_ROLE_CODES = {
    "member",
    "treasurer",
    "censor",
    "association_manager",
    "association_admin",
}


def _parse_date(raw: Any) -> Optional[date]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    s = str(raw).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_int(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    s = str(raw).replace(" ", "").replace(" ", "").replace(".", "").replace(",", "")
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


class MembersImporter(Importer):
    entity = "members"
    label = "Membres"
    description = "Liste des membres de l'association (nom, numéro, statut, adhésion…)."
    sheet_title = "Membres"

    columns = [
        ImportColumn("full_name", "Nom complet", required=True,
                     help="Nom et prénom du membre.", example="Awa Diallo"),
        ImportColumn("member_number", "Numéro d'adhérent",
                     help="Numéro interne du membre (facultatif mais recommandé).",
                     example="M-001"),
        ImportColumn("email", "Email",
                     help="Email de connexion. Obligatoire SAUF si vous mettez un "
                          "mot de passe ci-contre. Avec email et sans mot de passe, "
                          "un lien d'activation est envoyé par mail.",
                     example="awa.diallo@example.com"),
        ImportColumn("password", "Mot de passe",
                     help="Facultatif. Si renseigné : le membre se connecte avec ce "
                          "mot de passe (qu'il devra changer à la 1re connexion). "
                          "Si vide : un lien d'activation est envoyé à son email.",
                     example="Bienvenue2026"),
        ImportColumn("phone", "Téléphone",
                     help="Facultatif.", example="+237 6 99 00 11 22"),
        ImportColumn("status", "Statut", choices=_STATUS,
                     help="État de l'adhésion. Par défaut : Actif."),
        ImportColumn("category", "Catégorie", choices=_CATEGORY,
                     help="Type de membre. Par défaut : Actif."),
        ImportColumn("joined_at", "Date d'adhésion",
                     help="Format JJ/MM/AAAA. Par défaut : aujourd'hui.",
                     example="01/01/2020"),
        ImportColumn("roles", "Rôles",
                     help="Codes séparés par des virgules. Par défaut : member. "
                          "Valides : member, treasurer, censor, association_manager, "
                          "association_admin.",
                     example="member"),
        ImportColumn("cumulative_contributions", "Cotisations cumulées (ouverture)",
                     help="Solde d'ouverture facultatif. Ignoré si vous importez "
                          "aussi l'historique des séances.",
                     example="50000"),
        ImportColumn("notes", "Notes", help="Remarque libre facultative."),
    ]

    async def export_rows(self, db, association_id, ctx):
        from sqlalchemy.orm import selectinload
        from .export_helpers import is_placeholder_email

        res = await db.execute(
            select(Membership)
            .options(
                selectinload(Membership.user),
                selectinload(Membership.membership_roles).selectinload(MembershipRole.role),
            )
            .where(Membership.association_id == association_id)
            .order_by(Membership.member_number)
        )
        rows = []
        for m in res.scalars().all():
            user = m.user
            roles = ",".join(
                mr.role.code for mr in m.membership_roles if mr.role and mr.role.code != "member"
            )
            email = None if is_placeholder_email(getattr(user, "email", None)) else getattr(user, "email", None)
            rows.append({
                "full_name": getattr(user, "full_name", None),
                "member_number": m.member_number,
                "email": email,
                "password": None,  # non exportable
                "phone": getattr(user, "phone", None),
                "status": m.status,
                "category": m.category,
                "joined_at": m.joined_at,
                "roles": roles or None,
                "cumulative_contributions": m.cumulative_contributions or None,
                "notes": m.notes,
            })
        return rows

    async def new_ctx(self, db: AsyncSession, association_id) -> dict:
        assoc = (
            await db.execute(select(Association).where(Association.id == association_id))
        ).scalar_one()
        roles = (await db.execute(select(Role))).scalars().all()
        # Cache de liaison partagé (classeurs multi-feuilles) : n° d'adhérent →
        # membership_id. Préchargé avec les membres existants ; alimenté à la
        # création. Les feuilles « mouvements » s'en servent pour résoudre.
        existing = (
            await db.execute(
                select(Membership.member_number, Membership.id).where(
                    Membership.association_id == association_id,
                    Membership.member_number.isnot(None),
                )
            )
        ).all()
        return {
            "assoc": assoc,
            "roles_by_code": {r.code: r for r in roles},
            "seen_emails": set(),
            "seen_numbers": set(),
            "membership_by_number": {num: mid for num, mid in existing},
        }

    async def validate_row(self, db, association_id, values, ctx):
        errors: list[str] = []

        full_name = values.get("full_name")
        if not full_name:
            errors.append("Nom complet obligatoire.")

        email = values.get("email")
        if email:
            email = email.lower()
            if "@" not in email:
                errors.append(f"Email invalide : {email}.")
            elif email in ctx["seen_emails"]:
                errors.append(f"Email en double dans le fichier : {email}.")

        number = values.get("member_number")
        if number and number in ctx["seen_numbers"]:
            errors.append(f"Numéro d'adhérent en double dans le fichier : {number}.")

        status = values.get("status") or "active"
        if status not in {c.value for c in _STATUS}:
            errors.append(f"Statut invalide : {values.get('status')}.")

        category = values.get("category") or "active"
        if category not in {c.value for c in _CATEGORY}:
            errors.append(f"Catégorie invalide : {values.get('category')}.")

        joined_raw = values.get("joined_at")
        joined = _parse_date(joined_raw)
        if joined_raw and joined is None:
            errors.append(f"Date d'adhésion illisible : {joined_raw} (attendu JJ/MM/AAAA).")

        role_codes = ["member"]
        if values.get("roles"):
            role_codes = [c.strip() for c in str(values["roles"]).split(",") if c.strip()]
            for code in role_codes:
                if code not in _VALID_ROLE_CODES:
                    errors.append(f"Rôle inconnu : {code}.")

        cumul_raw = values.get("cumulative_contributions")
        cumul = _parse_int(cumul_raw)
        if cumul_raw and cumul is None:
            errors.append(f"Cotisations cumulées illisibles : {cumul_raw}.")

        password = values.get("password")
        if password is not None and len(password) < 6:
            errors.append("Mot de passe trop court (6 caractères minimum).")

        # Sans email ni mot de passe, le membre est créé pour le suivi mais SANS
        # accès (inactif). L'admin pourra lui ajouter un email/mot de passe plus
        # tard. C'est utile pour migrer d'anciens membres (juste nom + numéro).

        if errors:
            return None, errors

        if email:
            ctx["seen_emails"].add(email)
        if number:
            ctx["seen_numbers"].add(number)

        return {
            "full_name": full_name,
            "email": email,
            "password": password,
            "phone": values.get("phone"),
            "member_number": number,
            "status": status,
            "category": category,
            "joined_at": joined,
            "role_codes": role_codes,
            "cumulative_contributions": cumul or 0,
            "notes": values.get("notes"),
        }, []

    async def preview_register(self, payload, ctx):
        # Aperçu : simule la liaison n° → membre (id factice) pour les feuilles aval.
        num = payload.get("member_number")
        if num:
            ctx.setdefault("membership_by_number", {}).setdefault(num, "__preview__")

    async def create_row(self, db, association_id, payload, ctx):
        assoc: Association = ctx["assoc"]

        # Garde anti-double-import : un numéro d'adhérent déjà présent dans
        # l'association bloque la ligne (sécurise les membres sans email).
        number = payload["member_number"]
        if number:
            exists = (
                await db.execute(
                    select(Membership.id).where(
                        Membership.association_id == association_id,
                        Membership.member_number == number,
                    )
                )
            ).first()
            if exists is not None:
                raise ValueError(f"Numéro d'adhérent déjà utilisé : {number}.")

        # Résolution / création de l'utilisateur.
        password = payload.get("password")
        target: Optional[User] = None
        email = payload["email"]
        if email:
            target = (
                await db.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
        if target is None:
            real_email = bool(email)
            if not email:
                # Pas d'email mais un mot de passe (garanti par la validation) :
                # email-placeholder = identifiant de connexion.
                slug = (assoc.slug or "assoc")[:20]
                email = f"import-{uuid4().hex[:12]}@{slug}.import.local"
            target = User(
                full_name=payload["full_name"],
                email=email,
                phone=payload.get("phone"),
                groupement_id=assoc.groupement_id,
                user_type=UserType.MEMBER,
                # Mot de passe fourni → compte actif tout de suite ; sinon il
                # s'activera via le lien d'activation envoyé par mail.
                is_active=bool(password),
            )
            if password:
                target.hashed_password = get_password_hash(password)
                target.must_change_password = True  # à changer à la 1re connexion
            db.add(target)
            await db.flush()
        else:
            real_email = True  # utilisateur existant → a forcément un vrai email

        # Pas de doublon d'adhésion.
        dup = (
            await db.execute(
                select(Membership).where(
                    Membership.user_id == target.id,
                    Membership.association_id == association_id,
                )
            )
        ).scalar_one_or_none()
        if dup is not None:
            raise ValueError(f"{payload['full_name']} est déjà membre de cette association.")

        joined = payload["joined_at"] or date.today()
        membership = Membership(
            user_id=target.id,
            association_id=association_id,
            member_number=payload["member_number"],
            status=MembershipStatus(payload["status"]),
            category=MemberCategory(payload["category"]),
            joined_at=datetime(joined.year, joined.month, joined.day, tzinfo=timezone.utc),
            cumulative_contributions=payload["cumulative_contributions"],
            notes=payload["notes"],
        )
        db.add(membership)
        await db.flush()

        # Alimente le cache de liaison (classeurs multi-feuilles).
        if payload["member_number"]:
            ctx.setdefault("membership_by_number", {})[payload["member_number"]] = membership.id

        now = datetime.now(timezone.utc)
        for code in payload["role_codes"]:
            role = ctx["roles_by_code"].get(code)
            if role:
                db.add(MembershipRole(membership_id=membership.id, role_id=role.id, assigned_at=now))

        # Accès au compte : si pas de mot de passe mais un vrai email → invitation
        # + lien d'activation. L'envoi des mails est différé après le commit.
        plain_token: Optional[str] = None
        if real_email and not password:
            is_admin = any(c in _ADMIN_ROLE_CODES for c in payload["role_codes"])
            kind = InvitationKind.ASSOCIATION_ADMIN if is_admin else InvitationKind.ASSOCIATION_MEMBER
            plain_token = generate_invitation_token()
            db.add(
                Invitation(
                    email=target.email,
                    full_name=payload["full_name"],
                    kind=kind,
                    status=InvitationStatus.PENDING,
                    token_hash=hash_token(plain_token),
                    groupement_id=assoc.groupement_id,
                    association_id=assoc.id,
                    expires_at=Invitation.expiry_in(settings.INVITATION_EXPIRE_DAYS),
                )
            )

        # File des mails (bienvenue + activation) envoyés après le commit global.
        if real_email:
            ctx.setdefault("_email_queue", []).append(
                {
                    "email": target.email,
                    "name": payload["full_name"],
                    "has_password": bool(password),
                    "plain_token": plain_token,
                    "assoc_name": assoc.name,
                }
            )

    async def after_commit(self, db, ctx):
        """Envoie, après le commit, le mail de bienvenue (sans mot de passe) et,
        si pas de mot de passe, le mail d'activation séparé. Les échecs SMTP
        n'interrompent pas l'import."""
        for item in ctx.get("_email_queue", []):
            try:
                await send_account_created_email(
                    to=item["email"],
                    invitee_name=item["name"],
                    association_name=item["assoc_name"],
                    login_url=_login_url(),
                    has_default_password=item["has_password"],
                )
            except MailError:
                pass
            if item["plain_token"]:
                try:
                    await send_invitation_email(
                        to=item["email"],
                        invitee_name=item["name"],
                        activation_url=_activation_url(item["plain_token"]),
                        inviter_name=None,
                        groupement_name=item["assoc_name"],
                        role_label="Membre d'association",
                        expires_in_days=settings.INVITATION_EXPIRE_DAYS,
                    )
                except MailError:
                    pass
