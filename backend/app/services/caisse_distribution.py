"""Phase 7 — modèle Fred.

Service de clôture/redistribution des intérêts d'une caisse en mode
SHARED_PRO_RATA. Calcule l'intérêt encaissé pendant la période, le redistribue
aux cotisants au prorata de leur apport_cum_at_period_start, et reset le
snapshot pour la période suivante.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.caisse import (
    Caisse,
    CaisseContributorBalance,
    CaisseDistribution,
    CaisseDistributionShare,
    DistributionPeriod,
    InterestDistribution,
)
from app.models.loan import Loan, LoanRepayment
from app.models.user import User


def _period_label(period: str, start: date, end: date, meeting_title: str | None = None) -> str:
    """Étiquette humaine d'une période, selon le mode configuré."""
    if period == DistributionPeriod.PER_MEETING.value:
        return f"Séance du {end.strftime('%d/%m/%Y')}" + (f" — {meeting_title}" if meeting_title else "")
    if period == DistributionPeriod.MONTHLY.value:
        return end.strftime("%Y-%m")
    if period == DistributionPeriod.QUARTERLY.value:
        q = (end.month - 1) // 3 + 1
        return f"{end.year}-Q{q}"
    if period == DistributionPeriod.ANNUALLY.value:
        return str(end.year)
    return f"{start.isoformat()} → {end.isoformat()}"


async def close_distribution_period(
    db: AsyncSession,
    *,
    caisse: Caisse,
    period_end: date,
    closed_by: User,
    meeting_title: Optional[str] = None,
) -> CaisseDistribution:
    """Clôture la période courante d'une caisse SHARED_PRO_RATA.

    - Pool : Σ intérêts des LoanRepayment liés à des prêts dont la
      `source_caisse_id == caisse.id`, pour `paid_on` ∈ ]last_distribution_at,
      period_end].
    - Base : Σ apport_cum_at_period_start de tous les CaisseContributorBalance
      de la caisse. Lors de la 1re distribution (base = 0 partout), on
      retombe sur apport_cum (= tout ce qui a été cotisé jusque-là).
    - Reliquat d'arrondi : versé au dernier cotisant par ordre (created_at).
    - Effet : crée la Distribution + les Shares, met à jour
      `interest_cum`, snapshot `apport_cum_at_period_start = apport_cum`,
      `caisse.last_distribution_at = period_end`.

    Le caller commit.
    """
    if caisse.interest_distribution != InterestDistribution.SHARED_PRO_RATA.value:
        raise ValueError("La caisse n'est pas en mode SHARED_PRO_RATA.")

    period_start = caisse.last_distribution_at or caisse.created_at.date()

    pool_res = await db.execute(
        select(func.coalesce(func.sum(LoanRepayment.interest), 0))
        .join(Loan, Loan.id == LoanRepayment.loan_id)
        .where(
            Loan.source_caisse_id == caisse.id,
            LoanRepayment.paid_on > period_start,
            LoanRepayment.paid_on <= period_end,
        )
    )
    interest_pool = int(pool_res.scalar() or 0)

    balances_res = await db.execute(
        select(CaisseContributorBalance)
        .where(CaisseContributorBalance.caisse_id == caisse.id)
        .order_by(CaisseContributorBalance.created_at.asc())
    )
    balances = list(balances_res.scalars().all())

    # 1re distribution : pas de snapshot précédent → on prend apport_cum actuel.
    total_base_snapshot = sum(b.apport_cum_at_period_start for b in balances)
    if total_base_snapshot == 0:
        bases = {b.membership_id: b.apport_cum for b in balances}
    else:
        bases = {b.membership_id: b.apport_cum_at_period_start for b in balances}
    total_base = sum(bases.values())

    dist = CaisseDistribution(
        caisse_id=caisse.id,
        period_start=period_start,
        period_end=period_end,
        period_label=_period_label(
            caisse.distribution_period, period_start, period_end, meeting_title
        ),
        interest_pool=interest_pool,
        total_base=total_base,
        closed_at=datetime.now(timezone.utc),
        closed_by_id=closed_by.id,
    )
    db.add(dist)
    await db.flush()

    if total_base > 0 and interest_pool > 0:
        # Reliquat d'arrondi → dernier cotisant (par created_at) ayant base > 0.
        contributing = [b for b in balances if bases.get(b.membership_id, 0) > 0]
        n = len(contributing)
        accum = 0
        for i, b in enumerate(contributing):
            base = bases[b.membership_id]
            if i < n - 1:
                share = (interest_pool * base) // total_base
            else:
                share = interest_pool - accum
            if share <= 0:
                continue
            db.add(
                CaisseDistributionShare(
                    distribution_id=dist.id,
                    membership_id=b.membership_id,
                    base=base,
                    share_amount=share,
                )
            )
            b.interest_cum += share
            accum += share

    # Snapshot pour la prochaine période (look-back « à la Fred »).
    for b in balances:
        b.apport_cum_at_period_start = b.apport_cum

    caisse.last_distribution_at = period_end

    return dist


def is_period_due(caisse: Caisse, now: date) -> bool:
    """Détermine si une nouvelle distribution est due au regard de la cadence
    et de la dernière clôture. Renvoie True si on doit clôturer maintenant."""
    if caisse.interest_distribution != InterestDistribution.SHARED_PRO_RATA.value:
        return False
    last = caisse.last_distribution_at
    period = caisse.distribution_period
    if period == DistributionPeriod.PER_MEETING.value:
        return True  # à chaque séance close
    if last is None:
        return True  # 1re fois
    if period == DistributionPeriod.MONTHLY.value:
        return (now.year, now.month) > (last.year, last.month)
    if period == DistributionPeriod.QUARTERLY.value:
        q_now = (now.month - 1) // 3
        q_last = (last.month - 1) // 3
        return (now.year, q_now) > (last.year, q_last)
    if period == DistributionPeriod.ANNUALLY.value:
        return now.year > last.year
    return False
