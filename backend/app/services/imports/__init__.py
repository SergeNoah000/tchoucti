"""Registre des importers par entité."""
from __future__ import annotations

from .aid_types import AidTypesImporter
from .base import Importer
from .caisses import CaissesImporter
from .loan_types import LoanTypesImporter
from .members import MembersImporter
from .tontines import TontinesImporter

# Ordre = ordre d'affichage / de dépendance recommandé.
_IMPORTERS: list[Importer] = [
    MembersImporter(),
    CaissesImporter(),
    LoanTypesImporter(),
    AidTypesImporter(),
    TontinesImporter(),
]

REGISTRY: dict[str, Importer] = {imp.entity: imp for imp in _IMPORTERS}


def get_importer(entity: str) -> Importer | None:
    return REGISTRY.get(entity)


def list_importers() -> list[Importer]:
    return list(_IMPORTERS)
