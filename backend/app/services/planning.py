"""Meeting auto-planning — generate future meetings from an association's cadence.

Reads `Association.config.meetings`:
    frequency:        "weekly" | "biweekly" | "monthly" | "quarterly"   (default: monthly)
    day_of_week:      0–6 (Mon–Sun) for weekly/biweekly — optional
    default_title:    template used for each meeting title — supports {date}
    default_location: copied into each generated meeting
    horizon:          N (default 12) — target window of future PLANNED meetings

The cadence is best-effort: for monthly/quarterly we advance by calendar months
so dates stay aligned with the same day-of-month; for weekly/biweekly we move
by 7/14 days. The first generated date is the first cadence-aligned date that
is strictly after `anchor` (or `anchor` itself when it already aligns).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional, Sequence

from dateutil.relativedelta import relativedelta

from app.models.association import Association

DEFAULT_HORIZON = 12


def _cfg(assoc: Association) -> dict:
    return ((assoc.config or {}).get("meetings") or {})


def horizon(assoc: Association) -> int:
    """How many future PLANNED meetings the auto-extender targets."""
    v = _cfg(assoc).get("horizon")
    try:
        return max(1, int(v)) if v else DEFAULT_HORIZON
    except (TypeError, ValueError):
        return DEFAULT_HORIZON


def _align_to_weekday(d: date, target_dow: int) -> date:
    """Return the next date ≥ `d` whose weekday is `target_dow` (0=Mon)."""
    delta = (target_dow - d.weekday()) % 7
    return d + timedelta(days=delta)


def next_date_after(assoc: Association, last: Optional[date]) -> date:
    """Compute the next meeting date after `last` per the association cadence.

    If `last` is None, start "tomorrow-or-aligned": today + 1 cadence step from
    the cadence anchor.
    """
    cfg = _cfg(assoc)
    freq = (cfg.get("frequency") or "monthly").lower()
    dow_raw = cfg.get("day_of_week")
    target_dow: Optional[int] = None
    if dow_raw is not None:
        try:
            target_dow = int(dow_raw) % 7
        except (TypeError, ValueError):
            target_dow = None

    base = last or date.today()
    if freq == "weekly":
        nxt = base + timedelta(days=7) if last else base + timedelta(days=1)
        if target_dow is not None:
            nxt = _align_to_weekday(nxt, target_dow)
        return nxt
    if freq == "biweekly":
        nxt = base + timedelta(days=14) if last else base + timedelta(days=1)
        if target_dow is not None:
            nxt = _align_to_weekday(nxt, target_dow)
        return nxt
    if freq == "quarterly":
        nxt = (last + relativedelta(months=3)) if last else (base + relativedelta(months=3))
        return nxt
    # monthly (default)
    nxt = (last + relativedelta(months=1)) if last else (base + relativedelta(months=1))
    return nxt


def generate_dates(assoc: Association, count: int, start_from: Optional[date]) -> List[date]:
    """Return `count` future cadence-aligned dates, starting at/after `start_from`.

    `start_from` is the FIRST date to use (already aligned, or aligned-up to the
    cadence). When None, we start one cadence step after today.
    """
    if count <= 0:
        return []
    first = start_from or next_date_after(assoc, None)
    dates = [first]
    for _ in range(count - 1):
        dates.append(next_date_after(assoc, dates[-1]))
    return dates


def default_title(assoc: Association, d: date) -> str:
    """Title for a meeting scheduled on `d`. Picks user template if present."""
    tpl = _cfg(assoc).get("default_title") or "Séance du {date}"
    return tpl.replace("{date}", d.strftime("%d/%m/%Y"))


def default_location(assoc: Association) -> Optional[str]:
    return _cfg(assoc).get("default_location") or None


def reminder_offsets(assoc: Association) -> Sequence[int]:
    """Days-before offsets when reminders should fire (e.g. [7, 1])."""
    cfg = ((assoc.config or {}).get("notifications") or {}).get("meeting_reminders") or {}
    if cfg.get("enabled") is False:
        return ()
    raw = cfg.get("days_before") or [7, 1]
    out: List[int] = []
    for v in raw:
        try:
            n = int(v)
        except (TypeError, ValueError):
            continue
        if 0 <= n <= 60:
            out.append(n)
    return sorted(set(out), reverse=True)
