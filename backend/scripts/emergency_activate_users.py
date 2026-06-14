"""Dépannage : active TOUS les utilisateurs inactifs et leur donne un mot de
passe commun (utile après un import de membres, avant la fonctionnalité dédiée).

Usage (dans le conteneur backend) :
    docker compose exec -T backend python -m scripts.emergency_activate_users "MotDePasseCommun"

- Cible tous les User avec is_active = False.
- Active le compte (is_active = True) et fixe le mot de passe fourni.
- N'écrase un mot de passe existant que si l'utilisateur n'en avait pas
  (sécurité : on ne touche pas à un mot de passe déjà défini).
- Affiche la liste des comptes activés (nom + email de connexion).

⚠️ Demandez ensuite à chaque membre de changer son mot de passe.
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.core.security import get_password_hash
from app.db.session import AsyncSessionLocal
from app.models.user import User


async def main(common_password: str) -> None:
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(User).where(User.is_active.is_(False)))
        users = list(res.scalars().all())
        if not users:
            print("Aucun utilisateur inactif. Rien à faire.")
            return

        hashed = get_password_hash(common_password)
        activated: list[tuple[str, str, bool]] = []
        for u in users:
            had_password = bool(u.hashed_password)
            u.is_active = True
            if not had_password:
                u.hashed_password = hashed
            activated.append((u.full_name, u.email, had_password))

        await db.commit()

        print(f"\n✅ {len(activated)} compte(s) activé(s) :\n")
        print(f"{'Nom':<32} {'Email (identifiant)':<45} Mot de passe")
        print("-" * 95)
        for name, email, had_pwd in activated:
            pwd = "(inchangé — en avait déjà un)" if had_pwd else common_password
            print(f"{name:<32} {email:<45} {pwd}")
        print(
            "\nLes membres se connectent avec leur email ci-dessus + le mot de passe "
            "commun.\nDemandez-leur de le changer après la première connexion."
        )


if __name__ == "__main__":
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print('Usage : python -m scripts.emergency_activate_users "MotDePasseCommun"')
        raise SystemExit(1)
    asyncio.run(main(sys.argv[1]))
