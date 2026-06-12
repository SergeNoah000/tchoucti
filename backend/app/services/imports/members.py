"""Importer de MEMBRES.

Crée directement le User (sans email d'invitation) + la Membership + les rôles.
Un membre « papier » sans email reçoit un email placeholder unique (modifiable
plus tard) car ``User.email`` est obligatoire et unique globalement.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.association import Association
from app.models.role import (
    MemberCategory,
    Membership,
    MembershipRole,
    MembershipStatus,
    Role,
)
from app.models.user import User, UserType

from .base import Choice, ImportColumn, Importer

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
                     help="Facultatif. Si vide, le membre n'aura pas de compte de "
                          "connexion (vous pourrez en ajouter un plus tard).",
                     example="awa.diallo@example.com"),
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

    async def new_ctx(self, db: AsyncSession, association_id) -> dict:
        assoc = (
            await db.execute(select(Association).where(Association.id == association_id))
        ).scalar_one()
        roles = (await db.execute(select(Role))).scalars().all()
        return {
            "assoc": assoc,
            "roles_by_code": {r.code: r for r in roles},
            "seen_emails": set(),
            "seen_numbers": set(),
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

        if errors:
            return None, errors

        if email:
            ctx["seen_emails"].add(email)
        if number:
            ctx["seen_numbers"].add(number)

        return {
            "full_name": full_name,
            "email": email,
            "phone": values.get("phone"),
            "member_number": number,
            "status": status,
            "category": category,
            "joined_at": joined,
            "role_codes": role_codes,
            "cumulative_contributions": cumul or 0,
            "notes": values.get("notes"),
        }, []

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
        target: Optional[User] = None
        email = payload["email"]
        if email:
            target = (
                await db.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
        if target is None:
            if not email:
                slug = (assoc.slug or "assoc")[:20]
                email = f"import-{uuid4().hex[:12]}@{slug}.import.local"
            target = User(
                full_name=payload["full_name"],
                email=email,
                phone=payload.get("phone"),
                groupement_id=assoc.groupement_id,
                user_type=UserType.MEMBER,
                is_active=False,
            )
            db.add(target)
            await db.flush()

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

        now = datetime.now(timezone.utc)
        for code in payload["role_codes"]:
            role = ctx["roles_by_code"].get(code)
            if role:
                db.add(MembershipRole(membership_id=membership.id, role_id=role.id, assigned_at=now))
