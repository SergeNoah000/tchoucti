"""Idempotent DB bootstrap — runs on backend container startup.

Unlike ``app.db.seed`` (which drops everything), this only seeds when the
database is empty. On an already-populated DB it does nothing, so restarting
the stack never wipes data.

Usage (wired into docker-compose `command`):
    python -m app.db.init_db
"""
import asyncio

from sqlalchemy import text

from app.db.session import engine
from app.db.seed import create_tables, seed_demo_data, seed_rbac_data


async def _is_initialised() -> bool:
    """True if the `users` table exists and holds at least one row."""
    try:
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT count(*) FROM users"))
            return (res.scalar() or 0) > 0
    except Exception:
        # Table missing → fresh database.
        return False


async def main() -> None:
    if await _is_initialised():
        print("✅ Database already initialised — skipping seed.")
        await engine.dispose()
        return

    print("🌱 Empty database — creating tables and seeding demo data...")
    await create_tables()
    # RBAC must precede demo data: memberships need roles to attach to.
    await seed_rbac_data()
    await seed_demo_data()
    await engine.dispose()
    print("🎉 Database ready.")


if __name__ == "__main__":
    asyncio.run(main())
