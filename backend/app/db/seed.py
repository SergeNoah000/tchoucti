"""Seed script — creates tables + demo accounts.

Usage (inside the container):
    python -m app.db.seed
"""
import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import datetime, timezone

from sqlalchemy import select

from app.core.security import get_password_hash
from app.db.base import Base
from app.db.session import engine, AsyncSessionLocal
from app.models.user import User, UserType
from app.models.groupement import Groupement
from app.models.association import Association
from app.models.caisse import Caisse, CaisseCategory
from app.models.finance import Fund, FundKind, Treasury
from app.models.groupement_admin import GroupementAdmin
from app.models.role import Membership, MembershipRole, MembershipStatus, Role

# Make sure ALL models are imported so metadata is complete
import app.models  # noqa: F401


async def create_tables():
    """Drop-and-create all tables (dev only)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Tables created")


async def seed_demo_data():
    """Insert demo groupement + association + 4 demo users."""
    async with AsyncSessionLocal() as db:
        # Check if already seeded
        result = await db.execute(
            text("SELECT count(*) FROM users WHERE email = 'admin@tchoucti.cm'")
        )
        if result.scalar() > 0:
            print("⏭️  Demo data already exists, skipping.")
            return

        # 1. Demo groupement
        groupement = Groupement(
            name="Groupement Démo",
            slug="demo",
            subdomain="demo",
            description="Groupement de démonstration pour tester la plateforme",
            email="contact@demo.tchoucti.cm",
            country="Cameroun",
            city="Douala",
            primary_color="#0F766E",
        )
        db.add(groupement)
        await db.flush()  # get groupement.id

        # 2. Demo association — setup_complete=false will trigger the onboarding
        # wizard the first time the admin logs in.
        association = Association(
            name="Association Solidarité Démo",
            slug="solidarite-demo",
            description="Association de démonstration",
            groupement_id=groupement.id,
            currency="XAF",
            timezone="Africa/Douala",
            city="Douala",
            config={"setup_complete": False, "setup_step": 0},
        )
        db.add(association)
        await db.flush()

        # 2b. Treasury + system caisse "Caisse générale" for the demo association.
        treasury = Treasury(association_id=association.id, currency="XAF", balance=0)
        db.add(treasury)
        await db.flush()
        general_fund = Fund(
            treasury_id=treasury.id,
            kind=FundKind.GENERAL,
            ref_key="",
            name="Caisse générale",
            description="Fonds opérationnel de l'association.",
            is_system=True,
        )
        db.add(general_fund)
        await db.flush()
        db.add(
            Caisse(
                association_id=association.id,
                fund_id=general_fund.id,
                name="Caisse générale",
                slug="generale",
                description="Caisse principale de l'association (auto-créée, non supprimable).",
                category=CaisseCategory.SYSTEM,
                is_system=True,
            )
        )

        # 3. Users
        #
        # Role layout (post Phase 0 — only `association_admin` opens the config UI):
        #   admin@demo-asso.tchoucti.cm    → association_admin → wizard + config
        #   tresorier@demo.tchoucti.cm     → treasurer         → operational only
        #   secretaire@demo.tchoucti.cm    → secretary         → operational only
        #   membre@demo.tchoucti.cm        → member            → operational only
        users_data = [
            {
                "email": "admin@tchoucti.cm",
                "full_name": "Super Admin Tchoucti",
                "password": "admin123",
                "user_type": UserType.SUPER_ADMIN,
                "groupement_id": None,
            },
            {
                "email": "admin@demo.tchoucti.cm",
                "full_name": "Admin Groupement Démo",
                "password": "groupement123",
                "user_type": UserType.GROUPEMENT_ADMIN,
                "groupement_id": groupement.id,
            },
            {
                "email": "admin@demo-asso.tchoucti.cm",
                "full_name": "Admin Association Démo",
                "password": "assoc123",
                "user_type": UserType.ASSOCIATION_USER,
                "groupement_id": groupement.id,
                "membership_role": "association_admin",
            },
            {
                "email": "tresorier@demo.tchoucti.cm",
                "full_name": "Trésorier Démo",
                "password": "assoc123",
                "user_type": UserType.ASSOCIATION_USER,
                "groupement_id": groupement.id,
                "membership_role": "treasurer",
            },
            {
                "email": "secretaire@demo.tchoucti.cm",
                "full_name": "Secrétaire Association Démo",
                "password": "assoc123",
                "user_type": UserType.ASSOCIATION_USER,
                "groupement_id": groupement.id,
                "membership_role": "association_manager",
            },
            {
                "email": "membre@demo.tchoucti.cm",
                "full_name": "Membre Démo",
                "password": "membre123",
                "user_type": UserType.MEMBER,
                "groupement_id": groupement.id,
                "membership_role": "member",
            },
        ]

        created: dict[str, User] = {}
        for u in users_data:
            user = User(
                email=u["email"],
                full_name=u["full_name"],
                hashed_password=get_password_hash(u["password"]),
                user_type=u["user_type"],
                groupement_id=u["groupement_id"],
                is_active=True,
                is_verified=True,
                language="fr",
            )
            db.add(user)
            created[u["email"]] = user

        await db.flush()  # assign user ids

        # The groupement admin is the owner of the demo groupement.
        owner = created["admin@demo.tchoucti.cm"]
        db.add(
            GroupementAdmin(
                user_id=owner.id,
                groupement_id=groupement.id,
                is_owner=True,
            )
        )

        # 4. Memberships — wire each demo user to the demo association with
        # the role declared in users_data. Required so the role-based admin
        # check (`is_association_admin`) returns the right answer.
        role_codes = {u["membership_role"] for u in users_data if u.get("membership_role")}
        roles_res = await db.execute(select(Role).where(Role.code.in_(role_codes)))
        role_by_code = {r.code: r for r in roles_res.scalars().all()}
        missing = role_codes - role_by_code.keys()
        if missing:
            raise RuntimeError(
                f"RBAC seed missing roles {missing} — run seed_rbac before seed_demo."
            )

        now = datetime.now(timezone.utc)
        for u in users_data:
            role_code = u.get("membership_role")
            if not role_code:
                continue
            membership = Membership(
                user_id=created[u["email"]].id,
                association_id=association.id,
                status=MembershipStatus.ACTIVE,
                joined_at=now,
            )
            db.add(membership)
            await db.flush()
            db.add(
                MembershipRole(
                    membership_id=membership.id,
                    role_id=role_by_code[role_code].id,
                    assigned_at=now,
                )
            )

        await db.commit()
        print(
            f"✅ Demo data seeded ({len(users_data)} users + groupement + "
            f"association + memberships + system caisse)"
        )


async def seed_rbac_data():
    """Seed system roles and permissions."""
    from app.seeds.rbac import seed_rbac
    async with AsyncSessionLocal() as db:
        await seed_rbac(db)


async def main():
    print("🌱 Seeding Tchoucti database...")
    await create_tables()
    # RBAC roles MUST exist before demo data: demo memberships attach roles.
    await seed_rbac_data()
    await seed_demo_data()
    await engine.dispose()
    print("🎉 Done!")



if __name__ == "__main__":
    asyncio.run(main())
