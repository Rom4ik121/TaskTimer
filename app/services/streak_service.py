"""Goal streak helpers — consecutive days meeting daily quota + weekly freeze."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_meta, set_meta
from app.models import Goal, ProgressLog
from app.schemas import StreakInfo

STREAK_FREEZE_META = "streak_freeze_used_week"


def iso_week_key(d: date | None = None) -> str:
    """ISO week label ``YYYY-Www`` (Monday-based), e.g. ``2026-W37``."""
    day = d or date.today()
    y, w, _ = day.isocalendar()
    return f"{y}-W{w:02d}"


def freeze_week_stored(session: Session) -> str | None:
    """Return stored ISO week key, or None if missing/empty/corrupt."""
    try:
        raw = get_meta(session, STREAK_FREEZE_META)
    except Exception:
        return None
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or len(s) < 7:
        return None
    # Expect YYYY-Www
    if s[4:6] != "-W":
        return None
    return s


def is_freeze_active(session: Session, *, today: date | None = None) -> bool:
    """True when freeze was activated for the current ISO week."""
    day = today or date.today()
    stored = freeze_week_stored(session)
    if stored is None:
        return False
    return stored == iso_week_key(day)


def is_freeze_available(session: Session, *, today: date | None = None) -> bool:
    """True when the user may still activate freeze this ISO week."""
    return not is_freeze_active(session, today=today)


def activate_streak_freeze(
    session: Session, *, today: date | None = None
) -> bool:
    """Consume the once-per-ISO-week freeze. Returns True if newly activated.

    Idempotent within the week: second call returns False without changing meta.
    """
    day = today or date.today()
    key = iso_week_key(day)
    if is_freeze_active(session, today=day):
        return False
    try:
        set_meta(session, STREAK_FREEZE_META, key)
        session.commit()
        return True
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
        return False


def _day_totals(session: Session, goal_id: int) -> dict[date, float]:
    rows = session.execute(
        select(func.date(ProgressLog.logged_at), func.sum(ProgressLog.amount))
        .where(ProgressLog.goal_id == goal_id)
        .group_by(func.date(ProgressLog.logged_at))
    ).all()
    out: dict[date, float] = {}
    for day_val, total in rows:
        if isinstance(day_val, str):
            d = date.fromisoformat(day_val)
        elif isinstance(day_val, date):
            d = day_val
        else:
            continue
        out[d] = float(total or 0.0)
    return out


def _compute_streaks(
    day_ok: dict[date, bool],
    today: date,
    *,
    allow_one_gap: bool = False,
) -> tuple[int, int]:
    """Return (current_streak, best_streak).

    Current allows today incomplete. When ``allow_one_gap`` (weekly freeze),
    one missing day is bridged and does **not** count toward streak length;
    best streak ignores freeze (only real quota days).
    """
    if not day_ok and not allow_one_gap:
        return 0, 0

    # Best streak over all known days (no freeze bridging)
    all_days = sorted(day_ok.keys())
    best = 0
    run = 0
    prev: date | None = None
    for d in all_days:
        if not day_ok[d]:
            run = 0
            prev = d
            continue
        if prev is not None and d == prev + timedelta(days=1):
            run += 1
        else:
            run = 1
        best = max(best, run)
        prev = d

    # Current streak: walk back from today; if today incomplete, start yesterday.
    # Freeze (allow_one_gap) bridges exactly one missing day in that walk.
    start = today
    if not day_ok.get(today, False):
        start = today - timedelta(days=1)

    current = 0
    cursor = start
    gap_left = 1 if allow_one_gap else 0
    for _ in range(366 * 5):
        if day_ok.get(cursor, False):
            current += 1
            cursor -= timedelta(days=1)
            continue
        if gap_left > 0:
            gap_left -= 1
            cursor -= timedelta(days=1)
            continue
        break

    return current, best


def goal_streak(session: Session, goal: Goal, *, today: date | None = None) -> StreakInfo:
    today = today or date.today()
    totals = _day_totals(session, goal.id)
    # A day counts if quota met OR any progress log exists with amount > 0
    # Prefer quota: complete when logged >= daily_quota
    quota = goal.daily_quota if goal.daily_quota > 0 else 1.0
    day_ok: dict[date, bool] = {}
    for d, amt in totals.items():
        day_ok[d] = amt >= quota

    allow_gap = is_freeze_active(session, today=today)
    current, best = _compute_streaks(day_ok, today, allow_one_gap=allow_gap)
    today_complete = day_ok.get(today, False)
    return StreakInfo(
        goal_id=goal.id,
        title=goal.title,
        current_streak=current,
        best_streak=best,
        today_complete=today_complete,
    )


def all_streaks(session: Session) -> list[StreakInfo]:
    """Streaks for all active goals — one logs query, no per-goal N+1."""
    goals = list(
        session.scalars(
            select(Goal)
            .where(Goal.archived.is_(False))
            .order_by(Goal.created_at.desc())
        ).all()
    )
    if not goals:
        return []
    today = date.today()
    allow_gap = is_freeze_active(session, today=today)
    ids = [g.id for g in goals]
    rows = session.execute(
        select(
            ProgressLog.goal_id,
            func.date(ProgressLog.logged_at),
            func.sum(ProgressLog.amount),
        )
        .where(ProgressLog.goal_id.in_(ids))
        .group_by(ProgressLog.goal_id, func.date(ProgressLog.logged_at))
    ).all()
    totals_by_goal: dict[int, dict[date, float]] = {gid: {} for gid in ids}
    for gid, day_val, total in rows:
        if isinstance(day_val, str):
            d = date.fromisoformat(day_val)
        elif isinstance(day_val, date):
            d = day_val
        else:
            continue
        totals_by_goal[int(gid)][d] = float(total or 0.0)

    out: list[StreakInfo] = []
    for g in goals:
        totals = totals_by_goal.get(g.id, {})
        quota = g.daily_quota if g.daily_quota > 0 else 1.0
        day_ok = {d: amt >= quota for d, amt in totals.items()}
        current, best = _compute_streaks(day_ok, today, allow_one_gap=allow_gap)
        out.append(
            StreakInfo(
                goal_id=g.id,
                title=g.title,
                current_streak=current,
                best_streak=best,
                today_complete=day_ok.get(today, False),
            )
        )
    return out


def quota_calendar(
    session: Session,
    goal: Goal,
    *,
    days: int = 28,
    today: date | None = None,
) -> list[dict]:
    """Last ``days`` calendar entries for streak grid.

    Each item: ``{day, met, amount, is_today}``.
    """
    today = today or date.today()
    totals = _day_totals(session, goal.id)
    quota = goal.daily_quota if goal.daily_quota > 0 else 1.0
    out: list[dict] = []
    start = today - timedelta(days=days - 1)
    d = start
    while d <= today:
        amt = float(totals.get(d, 0.0))
        out.append(
            {
                "day": d,
                "met": amt >= quota,
                "amount": amt,
                "is_today": d == today,
            }
        )
        d += timedelta(days=1)
    return out
