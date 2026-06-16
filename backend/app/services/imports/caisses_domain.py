"""Classeur « Caisses » : Membres + Caisses (config) + Mouvements.

Feuille 1 (Membres) crée/relie les membres et alimente le cache n° → id.
Feuille 2 (Caisses) crée les caisses et alimente le cache nom → caisse.
Feuille 3 (Mouvements) rejoue les dépôts/retraits sur la trésorerie.
"""
from __future__ import annotations

from .base import DomainImporter
from .caisse_movements import CaisseMovementsSheet
from .caisses import CaissesImporter
from .members import MembersImporter


class CaissesDomainImporter(DomainImporter):
    entity = "caisses_book"
    label = "Caisses (classeur complet)"
    description = (
        "Classeur Caisses : membres, configuration des caisses, puis les "
        "mouvements (dépôts/retraits) historiques."
    )

    sheet_importers = [
        MembersImporter(),
        CaissesImporter(),
        CaisseMovementsSheet(),
    ]
