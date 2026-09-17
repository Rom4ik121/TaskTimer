"""Focus / Pomodoro timer sessions."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TimeSession
from app.schemas import TimeSessionCreate, TimeSessionUpdate


def list_sessions(
    session: Session,
    limit: int = 20,
    *,
    has_note: bool | None = None,
) -> list[TimeSession]:
    """Recent sessions; ``has_note=True`` keeps only rows with a non-empty note."""
    stmt = select(TimeSession).order_by(TimeSession.created_at.desc())
    if has_note is True:
        stmt = stmt.where(TimeSession.note.isnot(None), TimeSession.note != "")
    stmt = stmt.limit(limit)
    rows = list(session.scalars(stmt).all())
    if has_note is True:
        rows = [r for r in rows if (getattr(r, "note", None) or "").strip()]
    return rows


def get_active_session(session: Session) -> Optional[TimeSession]:
    """Return the most recent running or paused (not done) session."""
    stmt = (
        select(TimeSession)
        .where(TimeSession.status.in_(["running", "paused"]))
        .order_by(TimeSession.updated_at.desc())
        .limit(1)
    )
    return session.scalars(stmt).first()


def get_session_by_id(session: Session, sid: int) -> Optional[TimeSession]:
    return session.get(TimeSession, sid)


def create_session(session: Session, data: TimeSessionCreate) -> TimeSession:
    # Pause any currently running session
    active = get_active_session(session)
    if active and active.status == "running":
        _sync_remaining(active)
        active.status = "paused"
    ts = TimeSession(
        task_id=data.task_id,
        label=data.label,
        duration_sec=data.duration_sec,
        remaining_sec=data.duration_sec,
        status="paused",
        note=(data.note or ""),
    )
    session.add(ts)
    session.commit()
    session.refresh(ts)
    return ts


def _sync_remaining(ts: TimeSession) -> None:
    if ts.status == "running" and ts.started_at:
        elapsed = int((datetime.now() - ts.started_at).total_seconds())
        ts.remaining_sec = max(0, ts.remaining_sec - elapsed)
        ts.started_at = datetime.now()
        if ts.remaining_sec <= 0:
            ts.remaining_sec = 0
            ts.status = "done"
            ts.started_at = None


def tick(session: Session, sid: int) -> Optional[TimeSession]:
    """Sync remaining time for a running session."""
    ts = session.get(TimeSession, sid)
    if not ts:
        return None
    if ts.status == "running":
        _sync_remaining(ts)
        session.commit()
        session.refresh(ts)
    return ts


def play(session: Session, sid: int) -> Optional[TimeSession]:
    ts = session.get(TimeSession, sid)
    if not ts or ts.status == "done":
        return None
    # Pause others
    for other in list_sessions(session, limit=50):
        if other.id != sid and other.status == "running":
            _sync_remaining(other)
            other.status = "paused"
            other.started_at = None
    ts.status = "running"
    ts.started_at = datetime.now()
    session.commit()
    session.refresh(ts)
    return ts


def pause(session: Session, sid: int) -> Optional[TimeSession]:
    ts = session.get(TimeSession, sid)
    if not ts or ts.status != "running":
        return ts
    _sync_remaining(ts)
    if ts.status != "done":
        ts.status = "paused"
        ts.started_at = None
    session.commit()
    session.refresh(ts)
    return ts


def reset(session: Session, sid: int) -> Optional[TimeSession]:
    ts = session.get(TimeSession, sid)
    if not ts:
        return None
    ts.remaining_sec = ts.duration_sec
    ts.status = "paused"
    ts.started_at = None
    session.commit()
    session.refresh(ts)
    return ts


def complete(
    session: Session, sid: int, note: str | None = None
) -> Optional[TimeSession]:
    """Mark session done; optionally persist a focus note."""
    ts = session.get(TimeSession, sid)
    if not ts:
        return None
    if ts.status == "running":
        _sync_remaining(ts)
    ts.status = "done"
    ts.remaining_sec = max(0, int(ts.remaining_sec or 0))
    ts.started_at = None
    if note is not None:
        ts.note = (note or "").strip()
    session.commit()
    session.refresh(ts)
    return ts


def update_session(
    session: Session, sid: int, data: TimeSessionUpdate
) -> Optional[TimeSession]:
    ts = session.get(TimeSession, sid)
    if not ts:
        return None
    updates = data.model_dump(exclude_unset=True)
    if "duration_sec" in updates and "remaining_sec" not in updates:
        # When changing duration while paused, reset remaining
        if ts.status != "running":
            updates.setdefault("remaining_sec", updates["duration_sec"])
    if "note" in updates and updates["note"] is not None:
        updates["note"] = str(updates["note"]).strip()
    for key, value in updates.items():
        setattr(ts, key, value)
    session.commit()
    session.refresh(ts)
    return ts


def delete_session(session: Session, sid: int) -> bool:
    ts = session.get(TimeSession, sid)
    if not ts:
        return False
    session.delete(ts)
    session.commit()
    return True
