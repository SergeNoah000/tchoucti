"""Seed script — creates tables + demo accounts.

Usage (inside the container):
    python -m app.db.seed
"""
import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.db.base import Base
from app.db.session import engine, AsyncSessionLocal
from app.models.user import User, UserType
from app.models.groupement import Groupement
from app.models.association import Association
from app.models.groupement_admin import GroupementAdmin

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

        # 2. Demo association
        association = Association(
            name="Association Solidarité Démo",
            slug="solidarite-demo",
            description="Association de démonstration",
            groupement_id=groupement.id,
            currency="XAF",
            timezone="Africa/Douala",
            city="Douala",
        )
        db.add(association)
        await db.flush()

        # 3. Users
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
                "email": "secretaire@demo.tchoucti.cm",
                "full_name": "Secrétaire Association Démo",
                "password": "assoc123",
                "user_type": UserType.ASSOCIATION_USER,
                "groupement_id": groupement.id,
            },
            {
                "email": "membre@demo.tchoucti.cm",
                "full_name": "Membre Démo",
                "password": "membre123",
                "user_type": UserType.MEMBER,
                "groupement_id": groupement.id,
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

        await db.commit()
        print("✅ Demo data seeded (4 users + groupement + association + owner)")


async def seed_rbac_data():
    """Seed system roles and permissions."""
    from app.seeds.rbac import seed_rbac
    async with AsyncSessionLocal() as db:
        await seed_rbac(db)


async def main():
    print("🌱 Seeding Tchoucti database...")
    await create_tables()
    await seed_demo_data()
    await seed_rbac_data()
    await engine.dispose()
    print("🎉 Done!")



if __name__ == "__main__":
    asyncio.run(main())
