"""Catalogue système des permissions et rôles par défaut.

Exécuté par `alembic upgrade head` (via une migration data) ou manuellement
via `python -m app.seeds.rbac`.

PERMISSIONS (code = "domaine.action")
=====================================

Plateforme (super-admin) :
  platform.groupements.manage   — créer/suspendre/supprimer groupements
  platform.users.manage         — gestion users globale
  platform.audit.read           — accès logs audit complet

Groupement :
  groupement.read               — voir le groupement
  groupement.update             — modifier infos / branding
  groupement.associations.manage — créer/suspendre/supprimer assos du groupement
  groupement.users.manage       — gérer les admins associations
  groupement.billing.manage     — abonnement / facturation

Association :
  association.read              — voir l'asso (page accueil)
  association.update            — modifier infos / config
  members.read
  members.create
  members.update
  members.delete
  meetings.read
  meetings.manage               — créer, animer, clôturer une séance
  meetings.entries.manage       — saisir les activités en réunion
  meetings.entries.correct      — corriger / annuler une saisie validée
  activities.manage             — paramétrer les activités de l'asso
  treasury.read
  treasury.manage               — opérations manuelles, void
  loans.read
  loans.request                 — déposer une demande
  loans.approve                 — approuver / décaisser
  loans.write_off               — passer en perte / radier
  tontine.read
  tontine.manage                — créer cycle, fixer ordre, payer bénéficiaire
  aid.read
  aid.request
  aid.approve
  projects.read
  projects.manage
  documents.read
  documents.manage
  audit.read                    — log d'audit de l'asso
  reports.read                  — exports / PV / bilans
"""
import asyncio
from dataclasses import dataclass
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import Permission, Role, RolePermission, RoleScope



@dataclass(frozen=True)
class PermDef:
    code: str
    name: str
    category: str
    scope: RoleScope
    description: str = ""


PERMISSIONS: List[PermDef] = [
    # Platform
    PermDef("platform.groupements.manage", "Gérer les groupements", "platform", RoleScope.PLATFORM),
    PermDef("platform.users.manage", "Gérer tous les utilisateurs", "platform", RoleScope.PLATFORM),
    PermDef("platform.audit.read", "Lire les logs d'audit globaux", "platform", RoleScope.PLATFORM),

    # Groupement
    PermDef("groupement.read", "Voir le groupement", "groupement", RoleScope.GROUPEMENT),
    PermDef("groupement.update", "Modifier le groupement", "groupement", RoleScope.GROUPEMENT),
    PermDef("groupement.associations.manage", "Gérer les associations du groupement", "groupement", RoleScope.GROUPEMENT),
    PermDef("groupement.users.manage", "Gérer les admins d'association", "groupement", RoleScope.GROUPEMENT),
    PermDef("groupement.billing.manage", "Gérer l'abonnement", "groupement", RoleScope.GROUPEMENT),

    # Association — base
    PermDef("association.read", "Voir l'association", "association", RoleScope.ASSOCIATION),
    PermDef("association.update", "Modifier l'association", "association", RoleScope.ASSOCIATION),

    # Members
    PermDef("members.read", "Voir les membres", "members", RoleScope.ASSOCIATION),
    PermDef("members.create", "Ajouter des membres", "members", RoleScope.ASSOCIATION),
    PermDef("members.update", "Modifier des membres", "members", RoleScope.ASSOCIATION),
    PermDef("members.delete", "Supprimer / suspendre des membres", "members", RoleScope.ASSOCIATION),

    # Meetings
    PermDef("meetings.read", "Voir les réunions", "meetings", RoleScope.ASSOCIATION),
    PermDef("meetings.manage", "Créer / animer / clôturer une réunion", "meetings", RoleScope.ASSOCIATION),
    PermDef("meetings.entries.manage", "Saisir les activités en réunion", "meetings", RoleScope.ASSOCIATION),
    PermDef("meetings.entries.correct", "Corriger / annuler une saisie validée", "meetings", RoleScope.ASSOCIATION),

    # Activities
    PermDef("activities.manage", "Paramétrer les activités", "activities", RoleScope.ASSOCIATION),

    # Treasury
    PermDef("treasury.read", "Voir la trésorerie", "treasury", RoleScope.ASSOCIATION),
    PermDef("treasury.manage", "Opérations manuelles / annulations", "treasury", RoleScope.ASSOCIATION),

    # Loans
    PermDef("loans.read", "Voir les prêts", "loans", RoleScope.ASSOCIATION),
    PermDef("loans.request", "Déposer une demande de prêt", "loans", RoleScope.ASSOCIATION),
    PermDef("loans.approve", "Approuver / décaisser un prêt", "loans", RoleScope.ASSOCIATION),
    PermDef("loans.write_off", "Radier un prêt (perte)", "loans", RoleScope.ASSOCIATION),

    # Tontine
    PermDef("tontine.read", "Voir la tontine", "tontine", RoleScope.ASSOCIATION),
    PermDef("tontine.manage", "Gérer la tontine (cycle, ordre, payout)", "tontine", RoleScope.ASSOCIATION),

    # Social aid
    PermDef("aid.read", "Voir les dossiers d'assistance", "aid", RoleScope.ASSOCIATION),
    PermDef("aid.request", "Déposer une demande d'aide", "aid", RoleScope.ASSOCIATION),
    PermDef("aid.approve", "Valider / payer une aide", "aid", RoleScope.ASSOCIATION),

    # Projects
    PermDef("projects.read", "Voir les projets", "projects", RoleScope.ASSOCIATION),
    PermDef("projects.manage", "Créer / clôturer les projets", "projects", RoleScope.ASSOCIATION),

    # Documents
    PermDef("documents.read", "Voir les documents", "documents", RoleScope.ASSOCIATION),
    PermDef("documents.manage", "Uploader / supprimer des documents", "documents", RoleScope.ASSOCIATION),

    # Audit & reports
    PermDef("audit.read", "Voir le log d'audit", "audit", RoleScope.ASSOCIATION),
    PermDef("reports.read", "Exporter rapports / PV / bilans", "reports", RoleScope.ASSOCIATION),
]


@dataclass(frozen=True)
class RoleDef:
    code: str
    name: str
    scope: RoleScope
    permissions: List[str]
    description: str = ""


# ─── Bundles ───
ALL_ASSOC_PERMS = [p.code for p in PERMISSIONS if p.scope == RoleScope.ASSOCIATION]
ALL_GROUP_PERMS = [p.code for p in PERMISSIONS if p.scope == RoleScope.GROUPEMENT]
ALL_PLATFORM_PERMS = [p.code for p in PERMISSIONS if p.scope == RoleScope.PLATFORM]

# Rôle "membre simple" — accès en lecture seule sur les zones où il a un intérêt
MEMBER_BASIC_PERMS = [
    "association.read",
    "members.read",
    "meetings.read",
    "treasury.read",
    "loans.read", "loans.request",
    "tontine.read",
    "aid.read", "aid.request",
    "projects.read",
    "documents.read",
]

# Rôle "manager d'association" — peut animer les réunions, saisir, gérer membres
ASSOC_MANAGER_PERMS = MEMBER_BASIC_PERMS + [
    "members.create", "members.update",
    "meetings.manage", "meetings.entries.manage",
    "activities.manage",
    "treasury.read",
    "tontine.manage",
    "projects.manage",
    "documents.manage",
    "reports.read",
]


SYSTEM_ROLES: List[RoleDef] = [
    # Plateforme
    RoleDef(
        "super_admin",
        "Super Administrateur Plateforme",
        RoleScope.PLATFORM,
        ALL_PLATFORM_PERMS + ALL_GROUP_PERMS + ALL_ASSOC_PERMS,
        "Accès total à la plateforme (Langeao SARL).",
    ),
    # Groupement
    RoleDef(
        "groupement_admin",
        "Administrateur Groupement",
        RoleScope.GROUPEMENT,
        ALL_GROUP_PERMS + ALL_ASSOC_PERMS,
        "Gère toutes les associations de son groupement.",
    ),
    # Association — RBAC fonctionnel par défaut
    RoleDef(
        "association_admin",
        "Administrateur Association",
        RoleScope.ASSOCIATION,
        ALL_ASSOC_PERMS,
        "Pleins pouvoirs sur l'association (président par défaut).",
    ),
    RoleDef(
        "association_manager",
        "Manager Association",
        RoleScope.ASSOCIATION,
        ASSOC_MANAGER_PERMS,
        "Anime les réunions, gère membres et trésorerie courante.",
    ),
    RoleDef(
        "treasurer",
        "Trésorier",
        RoleScope.ASSOCIATION,
        MEMBER_BASIC_PERMS + [
            "treasury.read", "treasury.manage",
            "loans.read", "loans.approve",
            "aid.read", "aid.approve",
            "meetings.entries.manage", "meetings.entries.correct",
            "reports.read",
        ],
        "Gestion financière : prêts, aides, trésorerie.",
    ),
    RoleDef(
        "censor",
        "Censeur",
        RoleScope.ASSOCIATION,
        MEMBER_BASIC_PERMS + ["audit.read", "reports.read", "treasury.read"],
        "Contrôle et audit interne.",
    ),
    RoleDef(
        "member",
        "Membre",
        RoleScope.ASSOCIATION,
        MEMBER_BASIC_PERMS,
        "Adhérent standard de l'association.",
    ),
]


# ─── Insertion function ───────────────────────────────────────────────────────

async def seed_rbac(db: AsyncSession) -> None:
    """Upsert all system permissions and roles into the database."""

    # 1. Upsert permissions
    perm_map: dict[str, Permission] = {}
    for pdef in PERMISSIONS:
        res = await db.execute(select(Permission).where(Permission.code == pdef.code))
        perm = res.scalar_one_or_none()
        if not perm:
            perm = Permission(
                code=pdef.code,
                name=pdef.name,
                description=pdef.description,
                category=pdef.category,
                scope=pdef.scope,
            )
            db.add(perm)
            await db.flush()
        perm_map[pdef.code] = perm

    # 2. Upsert system roles
    for rdef in SYSTEM_ROLES:
        res = await db.execute(
            select(Role).where(Role.code == rdef.code, Role.is_system == True)  # noqa: E712
        )
        role = res.scalar_one_or_none()
        if not role:
            role = Role(
                code=rdef.code,
                name=rdef.name,
                description=rdef.description,
                scope=rdef.scope,
                is_system=True,
            )
            db.add(role)
            await db.flush()

        # Sync permissions (add missing, keep existing)
        res = await db.execute(
            select(RolePermission).where(RolePermission.role_id == role.id)
        )
        existing_perm_ids = {rp.permission_id for rp in res.scalars().all()}

        for code in set(rdef.permissions):  # deduplicate
            perm = perm_map.get(code)
            if perm and perm.id not in existing_perm_ids:
                db.add(RolePermission(role_id=role.id, permission_id=perm.id))

    await db.commit()
    print(f"✅ RBAC seeded: {len(PERMISSIONS)} permissions, {len(SYSTEM_ROLES)} roles")


if __name__ == "__main__":
    from app.db.session import AsyncSessionLocal

    async def _main():
        async with AsyncSessionLocal() as db:
            await seed_rbac(db)

    asyncio.run(_main())

