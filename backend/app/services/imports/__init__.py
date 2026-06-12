"""Registre des importers par entité."""
from __future__ import annotations

from .base import Importer
from .members import MembersImporter

# Ordre = ordre d'affichage / de dépendance recommandé.
_IMPORTERS: list[Importer] = [
    MembersImporter(),
]

REGISTRY: dict[str, Importer] = {imp.entity: imp for imp in _IMPORTERS}


def get_importer(entity: str) -> Importer | None:
    return REGISTRY.get(entity)


def list_importers() -> list[Importer]:
    return list(_IMPORTERS)
