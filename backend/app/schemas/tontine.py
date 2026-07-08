"""Pydantic schemas for the tontine module (Phase 6A — Tontine → Cycles)."""
from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ── Inputs ──────────────────────────────────────────────────────────────────

class TontineCreate(BaseModel):
    """Crée une tontine (entité durable) + son 1er cycle + ses séances d'office."""

    association_id: UUID
    name: str = Field(..., min_length=2, max_length=150)
    description: Optional[str] = Field(None, max_length=500)
    round_amount: int = Field(..., gt=0, description="Montant (argent) OU quantité (avoir) par participant et par tour")

    # Nature de la cotisation : argent ou avoir physique (nom + quantité, sans argent).
    contribution_kind: str = Field("money", pattern=r"^(money|asset)$")
    asset_label: Optional[str] = Field(None, max_length=120)

    # Cadence des séances/tours
    frequency: str = Field("monthly", pattern=r"^(weekly|biweekly|monthly|bimonthly|custom)$")
    custom_interval_days: Optional[int] = Field(None, ge=1, le=365)

    # Mode de calcul du cycle.
    cycle_mode: str = Field("by_beneficiaries", pattern=r"^(by_beneficiaries|by_duration)$")
    beneficiaries_per_round: int = Field(1, ge=1, le=20)
    target_rounds: Optional[int] = Field(None, ge=1, le=120)  # nb max de séances (mode by_duration)
    beneficiary_pays: bool = True
    selection_method: str = Field("manual", pattern=r"^(manual|random|seniority|vote|auction|need)$")

    start_date: date
    is_mandatory: bool = True

    # Participants dans l'ordre de passage souhaité. Un même membre peut apparaître
    # PLUSIEURS fois = plusieurs noms/parts (chacun sa position dans la rotation).
    # Peut être vide : cycle brouillon, membres ajoutés ensuite depuis la config.
    participant_ids: List[UUID] = Field(default_factory=list, max_length=400)
    # Libellés parallèles (même longueur que participant_ids). None = nom du membre.
    participant_names: Optional[List[Optional[str]]] = None
    # Si is_mandatory=False : membres actifs explicitement exclus du cycle.
    excluded_membership_ids: List[UUID] = Field(default_factory=list)
    # Mélanger l'ordre de passage (tirage au sort).
    shuffle: bool = False

    @model_validator(mode="after")
    def _check(self):
        if self.contribution_kind == "asset" and not (self.asset_label and self.asset_label.strip()):
            raise ValueError("Le nom de l'avoir physique est requis.")
        if self.cycle_mode == "by_duration" and not self.target_rounds:
            raise ValueError("La durée max (nombre de séances) est requise en mode 'by_duration'.")
        return self


class NextCycleCreate(BaseModel):
    """Génère le cycle suivant — hérite de tout, ajuste juste la date de départ."""

    start_date: Optional[date] = None  # défaut : 1 cadence après la fin du cycle précédent


class CycleParticipantsUpdate(BaseModel):
    """Définit/édite les participants d'un cycle BROUILLON, puis (re)génère ses
    tours + séances. N'est possible que tant que le cycle est en brouillon."""

    participant_ids: List[UUID] = Field(default_factory=list, max_length=400)
    participant_names: Optional[List[Optional[str]]] = None
    excluded_membership_ids: List[UUID] = Field(default_factory=list)
    is_mandatory: bool = True
    shuffle: bool = False
    start_date: Optional[date] = None


class BeneficiaryRename(BaseModel):
    """Renomme un nom/part d'un bénéficiaire (admin + bureau, à tout moment)."""
    name: str = Field(..., min_length=1, max_length=150)


class CycleReorder(BaseModel):
    """Réordonne l'ordre de passage : nouvelle séquence des bénéficiaires des
    tours PAS ENCORE servis (brouillon = tous les tours ; cycle actif = tours
    futurs). La liste doit être une permutation exacte des bénéficiaires actuels
    de ces tours."""

    ordered_membership_ids: List[UUID] = Field(..., max_length=400)


# ── Outputs ─────────────────────────────────────────────────────────────────

class TontineBeneficiaryOut(BaseModel):
    id: UUID
    membership_id: UUID
    name: Optional[str] = None          # libellé du nom (name_label) ou nom du membre
    member_name: Optional[str] = None   # nom du membre porteur (pour le regroupement)
    share_amount: int
    share_parts: int


class TontineRoundOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    round_number: int
    scheduled_date: Optional[date]
    paid_out_date: Optional[date]
    beneficiaries: List[TontineBeneficiaryOut] = []
    expected_amount: int
    collected_amount: int
    paid_out_amount: int
    status: str
    meeting_id: Optional[UUID] = None
    meeting_title: Optional[str] = None


class TontineCycleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tontine_id: UUID
    cycle_number: int
    round_amount: int
    rounds_count: int
    current_round_number: int
    start_date: date
    end_date: Optional[date]
    order_strategy: str
    status: str
    is_mandatory: bool = True
    created_at: datetime


class TontineCycleDetail(TontineCycleOut):
    rounds: List[TontineRoundOut] = []
    pot_amount: int = 0


class TontineOut(BaseModel):
    """La tontine durable + un résumé de son cycle courant."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    association_id: UUID
    name: str
    slug: str
    description: Optional[str]
    is_active: bool
    round_amount: int
    contribution_kind: str = "money"
    asset_label: Optional[str] = None
    frequency: str
    custom_interval_days: Optional[int]
    cycle_mode: str = "by_beneficiaries"
    beneficiaries_per_round: int
    target_rounds: Optional[int] = None
    beneficiary_pays: bool
    selection_method: str
    created_at: datetime
    cycles_count: int = 0
    current_cycle: Optional[TontineCycleOut] = None


class TontineDetail(TontineOut):
    # En détail, le cycle courant porte ses tours (TontineCycleDetail).
    current_cycle: Optional[TontineCycleDetail] = None
    cycles: List[TontineCycleDetail] = []
