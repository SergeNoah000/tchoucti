"""Schémas du résumé d'activité d'un membre sur une période.

Alimente la page détail membre : cotisations (tontine/caisse/aide), demandes
(prêts/aides) et revenus (versements reçus), avec deux lectures possibles côté
frontend (chronologique ou groupé par activité) à partir des mêmes listes.
"""
from datetime import date as _date
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel


class ActivityItem(BaseModel):
    # Date de l'événement (séance pour les cotisations, demande, ou mouvement).
    # NB : import aliasé (_date) car le champ s'appelle `date` et masquerait le type.
    date: Optional[_date] = None
    # Famille : cotisation → tontine|caisse|aid ; demande → loan|aid ;
    # revenu → tontine_payout|loan_disbursement|aid_payout.
    kind: str
    label: str
    amount: int
    reference: Optional[str] = None
    status: Optional[str] = None
    meeting_title: Optional[str] = None


class MemberActivity(BaseModel):
    membership_id: UUID
    member_name: Optional[str] = None
    member_number: Optional[str] = None
    since: Optional[_date] = None
    until: Optional[_date] = None
    currency: Optional[str] = None

    contributions: List[ActivityItem] = []
    requests: List[ActivityItem] = []
    incomes: List[ActivityItem] = []

    # Totaux agrégés : {contributed, requested, received} + ventilations par famille.
    totals: Dict[str, int] = {}
    contributions_by_kind: Dict[str, int] = {}
    incomes_by_kind: Dict[str, int] = {}
