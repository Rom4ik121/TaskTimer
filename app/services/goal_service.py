"""Goal and progress logging service."""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_meta, set_meta
from app.models import AppMeta, Goal, ProgressLog
from app.schemas import GoalCreate, GoalUpdate, ProgressLogCreate, ProgressLogUpdate

CELEBRATED_META_PREFIX = "celebrated_goal_"


def list_goals(
    session: Session,
    *,
    archived: Optional[bool] = False,
    sort: Optional[str] = None,
) -> list[Goal]:
    """List goals. ``archived`` False=active, True=only archived, None=both.

    ``sort``: None/default → created_at desc; ``"percent"`` → percent_complete
    descending (most done first), then created_at desc as tiebreaker.
    """
    stmt = select(Goal)
    if archived is True:
        stmt = stmt.where(Goal.archived.is_(True))
    elif archived is False:
        stmt = stmt.where(Goal.archived.is_(False))
    goals = list(session.scalars(stmt).all())
    if sort == "percent":
        goals.sort(
            key=lambda g: (
                -float(getattr(g, "percent_complete", 0) or 0),
                -(g.created_at.timestamp() if g.created_at else 0),
            )
        )
    else:
        goals.sort(
            key=lambda g: -(g.created_at.timestamp() if g.created_at else 0)
        )
    return goals


def get_goal(session: Session, goal_id: int) -> Optional[Goal]:
    return session.get(Goal, goal_id)


def create_goal(session: Session, data: GoalCreate) -> Goal:
    goal = Goal(**data.model_dump())
    session.add(goal)
    session.commit()
    session.refresh(goal)
    return goal


def update_goal(session: Session, goal_id: int, data: GoalUpdate) -> Optional[Goal]:
    goal = session.get(Goal, goal_id)
    if not goal:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        # current_value is derived from logs — ignore direct writes
        if key == "current_value":
            continue
        setattr(goal, key, value)
    _recalc_current(session, goal)
    session.commit()
    session.refresh(goal)
    return goal


def delete_goal(session: Session, goal_id: int) -> bool:
    goal = session.get(Goal, goal_id)
    if not goal:
        return False
    # Drop celebration flag so reused SQLite rowids do not inherit it
    key = celebrated_meta_key(goal_id)
    meta = session.get(AppMeta, key)
    if meta is not None:
        session.delete(meta)
    session.delete(goal)
    session.commit()
    return True


def archive_goal(session: Session, goal_id: int) -> Optional[Goal]:
    return update_goal(session, goal_id, GoalUpdate(archived=True))


def unarchive_goal(session: Session, goal_id: int) -> Optional[Goal]:
    return update_goal(session, goal_id, GoalUpdate(archived=False))


def _recalc_current(session: Session, goal: Goal) -> None:
    """Set goal.current_value = min(target, sum(logs)). Does not commit."""
    total = session.scalar(
        select(func.coalesce(func.sum(ProgressLog.amount), 0.0)).where(
            ProgressLog.goal_id == goal.id
        )
    )
    goal.current_value = min(goal.target_value, float(total or 0.0))


def recalc_goal(session: Session, goal_id: int) -> Optional[Goal]:
    """Recalculate one goal's current_value from its progress logs."""
    goal = session.get(Goal, goal_id)
    if not goal:
        return None
    _recalc_current(session, goal)
    session.commit()
    session.refresh(goal)
    return goal


def repair_all_goal_values(session: Session) -> int:
    """Recalc current_value for every goal. Returns number of goals that drifted."""
    goals = list(session.scalars(select(Goal)).all())
    fixed = 0
    for g in goals:
        before = float(g.current_value or 0.0)
        _recalc_current(session, g)
        if abs(before - float(g.current_value or 0.0)) > 1e-9:
            fixed += 1
    session.commit()
    return fixed


def add_progress(session: Session, data: ProgressLogCreate) -> Optional[ProgressLog]:
    goal = session.get(Goal, data.goal_id)
    if not goal:
        return None
    log = ProgressLog(goal_id=data.goal_id, amount=data.amount, note=data.note)
    session.add(log)
    session.flush()
    _recalc_current(session, goal)
    session.commit()
    session.refresh(log)
    return log



def celebrated_meta_key(goal_id: int) -> str:
    return f"{CELEBRATED_META_PREFIX}{int(goal_id)}"


def celebrate_if_complete(session: Session, goal_id: int) -> str | None:
    """Once per goal: when current_value reaches target, set meta and return RU snack.

    Safe if goal missing or already celebrated. Commits the meta write.
    """
    goal = session.get(Goal, goal_id)
    if not goal:
        return None
    if float(goal.target_value or 0) <= 0:
        return None
    if float(goal.current_value or 0) + 1e-9 < float(goal.target_value):
        return None
    key = celebrated_meta_key(goal_id)
    if get_meta(session, key) == "1":
        return None
    set_meta(session, key, "1")
    session.commit()
    title = (goal.title or "Цель").strip() or "Цель"
    return f"🎉 Цель достигнута: «{title}»!"


def clear_celebrated_flags(session: Session) -> int:
    """Delete all celebrated_goal_* app_meta keys (dev/reset for re-testing snacks).

    Returns number of keys removed. Commits.
    """
    rows = list(
        session.scalars(
            select(AppMeta).where(AppMeta.key.like(f"{CELEBRATED_META_PREFIX}%"))
        ).all()
    )
    n = 0
    for row in rows:
        session.delete(row)
        n += 1
    session.commit()
    return n


def update_log(
    session: Session, log_id: int, data: ProgressLogUpdate
) -> Optional[ProgressLog]:
    log = session.get(ProgressLog, log_id)
    if not log:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(log, key, value)
    session.flush()  # ensure SUM sees updated amount
    goal = session.get(Goal, log.goal_id)
    if goal:
        _recalc_current(session, goal)
    session.commit()
    session.refresh(log)
    return log


def delete_log(session: Session, log_id: int) -> bool:
    log = session.get(ProgressLog, log_id)
    if not log:
        return False
    goal_id = log.goal_id
    session.delete(log)
    session.flush()
    goal = session.get(Goal, goal_id)
    if goal:
        _recalc_current(session, goal)
    session.commit()
    return True


def list_logs(session: Session, goal_id: int, limit: int = 50) -> list[ProgressLog]:
    stmt = (
        select(ProgressLog)
        .where(ProgressLog.goal_id == goal_id)
        .order_by(ProgressLog.logged_at.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt).all())



def days_to_complete(goal: Goal) -> int | None:
    """Estimate whole days left at daily_quota pace.

    Returns 0 when already at/above target, None when quota is invalid.
    Uses ceil(remaining / daily_quota).
    """
    remaining = float(goal.target_value) - float(goal.current_value or 0.0)
    if remaining <= 0:
        return 0
    quota = float(goal.daily_quota or 0.0)
    if quota <= 0:
        return None
    return int(math.ceil(remaining / quota))


def today_logged(session: Session, goal_id: int, day: Optional[date] = None) -> float:
    day = day or date.today()
    start = datetime.combine(day, datetime.min.time())
    end = datetime.combine(day, datetime.max.time())
    total = session.scalar(
        select(func.coalesce(func.sum(ProgressLog.amount), 0.0))
        .where(ProgressLog.goal_id == goal_id)
        .where(ProgressLog.logged_at >= start)
        .where(ProgressLog.logged_at <= end)
    )
    return float(total or 0.0)


def today_quotas(session: Session) -> list[dict]:
    """Per-goal today progress vs daily_quota (active goals only).

    Single aggregated query for today's logs (no per-goal N+1).
    """
    goals = list_goals(session, archived=False)
    if not goals:
        return []
    day = date.today()
    start = datetime.combine(day, datetime.min.time())
    end = datetime.combine(day, datetime.max.time())
    rows = session.execute(
        select(ProgressLog.goal_id, func.coalesce(func.sum(ProgressLog.amount), 0.0))
        .where(ProgressLog.goal_id.in_([g.id for g in goals]))
        .where(ProgressLog.logged_at >= start)
        .where(ProgressLog.logged_at <= end)
        .group_by(ProgressLog.goal_id)
    ).all()
    by_goal = {int(gid): float(total or 0.0) for gid, total in rows}
    out: list[dict] = []
    for g in goals:
        logged = by_goal.get(g.id, 0.0)
        out.append(
            {
                "goal": g,
                "today": logged,
                "quota": g.daily_quota,
                "complete": logged >= g.daily_quota,
                "ratio": min(1.0, logged / g.daily_quota) if g.daily_quota > 0 else 0.0,
            }
        )
    return out
