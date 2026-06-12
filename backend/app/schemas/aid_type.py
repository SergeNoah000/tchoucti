"""Pydantic schemas pour AidType — configuration simplifiée des aides sociales.

Un type d'aide = un NOM + une SOURCE + un MONTANT à donner au demandeur :

- Source INDIVIDUELLE (``funding_mode = "member_insurance"``) : une caisse
  individuelle (assurance) — type PERSONAL. Au décaissement, le montant est
  divisé par le nombre de membres et chaque membre est débité de cette part
  sur sa propre caisse.
- Source COLLECTIVE (``funding_mode = "fixed"``) : une caisse partagée
  (secours) — type COLLECTIVE/PROJECT. Le montant est entièrement prélevé sur
  cette caisse.

Les anciens champs (cotisation récurrente, objectif, caisse temporaire) restent
en base mais ne sont plus pilotés par l'UI : valeurs neutres par défaut.
"""
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Exposé à l'UI : individuelle (assurance) vs collective (secours).
FundingMode = Literal["member_insurance", "fixed"]
AmountMode = Literal["ceiling", "objective"]


class AidTypeCreate(BaseModel):
    association_id: UUID

    name: str = Field(..., min_length=2, max_length=150)
    slug: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = Field(None, max_length=1000)

    # Source du financement.
    funding_mode: FundingMode = "fixed"
    # Mode "fixed" (collective) : caisse partagée d'où sort tout le montant.
    source_caisse_id: Optional[UUID] = None
    # Mode "member_insurance" (individuelle) : caisse PERSONAL d'assurance.
    insurance_caisse_id: Optional[UUID] = None

    # Montant à donner au demandeur.
    aid_ceiling_amount: int = Field(0, ge=0)

    # ── Champs hérités, neutralisés (conservés pour compat DB) ────────────────
    auto_create_caisse: bool = False
    insurance_minimum: int = Field(0, ge=0)
    refill_period_days: int = Field(90, ge=1, le=730)
    member_contribution_amount: int = Field(0, ge=0)
    is_contribution_recurring: bool = False
    amount_mode: AmountMode = "ceiling"
    objective_amount: int = Field(0, ge=0)
    # 0 = illimité / pas de délai (l'UI simplifiée ne les expose plus).
    max_claims_per_member_per_year: int = Field(0, ge=0, le=20)
    declaration_delay_days: int = Field(0, ge=0, le=365)

    @model_validator(mode="after")
    def _check(self):
        self.auto_create_caisse = False
        self.amount_mode = "ceiling"
        self.objective_amount = 0
        if self.funding_mode == "member_insurance":
            # Source individuelle : une caisse d'assurance existante est requise.
            self.source_caisse_id = None
            if self.insurance_caisse_id is None:
                raise ValueError(
                    "Une caisse individuelle (assurance) est requise pour une source individuelle."
                )
        else:  # fixed = collective
            self.insurance_caisse_id = None
            if self.source_caisse_id is None:
                raise ValueError(
                    "Une caisse collective (secours) est requise pour une source collective."
                )
        if self.aid_ceiling_amount <= 0:
            raise ValueError("Le montant à donner doit être supérieur à 0.")
        return self


class AidTypeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    description: Optional[str] = Field(None, max_length=1000)
    is_active: Optional[bool] = None

    funding_mode: Optional[FundingMode] = None
    source_caisse_id: Optional[UUID] = None
    insurance_caisse_id: Optional[UUID] = None
    aid_ceiling_amount: Optional[int] = Field(None, ge=0)

    # Hérités (rarement modifiés depuis l'UI simplifiée).
    auto_create_caisse: Optional[bool] = None
    insurance_minimum: Optional[int] = Field(None, ge=0)
    refill_period_days: Optional[int] = Field(None, ge=1, le=730)
    member_contribution_amount: Optional[int] = Field(None, ge=0)
    is_contribution_recurring: Optional[bool] = None
    amount_mode: Optional[AmountMode] = None
    objective_amount: Optional[int] = Field(None, ge=0)
    max_claims_per_member_per_year: Optional[int] = Field(None, ge=0, le=20)
    declaration_delay_days: Optional[int] = Field(None, ge=0, le=365)


class AidTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    association_id: UUID
    funding_mode: str = "fixed"
    source_caisse_id: Optional[UUID] = None
    source_caisse_name: Optional[str] = None
    auto_create_caisse: bool = False
    insurance_caisse_id: Optional[UUID] = None
    insurance_caisse_name: Optional[str] = None
    insurance_minimum: int = 0
    refill_period_days: int = 90
    name: str
    slug: str
    description: Optional[str]
    is_active: bool

    member_contribution_amount: int
    is_contribution_recurring: bool
    amount_mode: str = "ceiling"
    aid_ceiling_amount: int
    objective_amount: int = 0
    max_claims_per_member_per_year: int
    declaration_delay_days: int
