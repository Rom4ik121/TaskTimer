"""Subtask / checklist CRUD for tasks."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Subtask, Task
from app.schemas import SubtaskCreate, SubtaskUpdate


def list_subtasks(session: Session, task_id: int) -> list[Subtask]:
    stmt = (
        select(Subtask)
        .where(Subtask.task_id == task_id)
        .order_by(Subtask.position.asc(), Subtask.id.asc())
    )
    return list(session.scalars(stmt).all())


def get_subtask(session: Session, subtask_id: int) -> Optional[Subtask]:
    return session.get(Subtask, subtask_id)


def create_subtask(session: Session, data: SubtaskCreate) -> Optional[Subtask]:
    task = session.get(Task, data.task_id)
    if not task:
        return None
    pos = data.position
    if pos is None:
        max_pos = session.scalar(
            select(func.max(Subtask.position)).where(Subtask.task_id == data.task_id)
        )
        pos = 0 if max_pos is None else int(max_pos) + 1
    sub = Subtask(
        task_id=data.task_id,
        title=data.title,
        done=data.done,
        position=pos,
    )
    session.add(sub)
    session.commit()
    session.refresh(sub)
    return sub


def update_subtask(
    session: Session, subtask_id: int, data: SubtaskUpdate
) -> Optional[Subtask]:
    sub = session.get(Subtask, subtask_id)
    if not sub:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(sub, key, value)
    session.commit()
    session.refresh(sub)
    return sub


def _auto_complete_enabled(session: Session) -> bool:
    from app.db import get_meta

    raw = get_meta(session, "auto_complete_subtasks")
    if raw is None:
        return False
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _maybe_auto_complete_parent(session: Session, task_id: int) -> None:
    """If setting on and all subtasks done, mark parent done via set_status (recur-safe)."""
    if not _auto_complete_enabled(session):
        return
    subs = list_subtasks(session, task_id)
    if not subs or not all(s.done for s in subs):
        return
    task = session.get(Task, task_id)
    if not task or task.status == "done":
        return
    from app.services import task_service

    task_service.set_status(session, task_id, "done")


def toggle_subtask(session: Session, subtask_id: int) -> Optional[Subtask]:
    sub = session.get(Subtask, subtask_id)
    if not sub:
        return None
    sub.done = not sub.done
    session.commit()
    session.refresh(sub)
    if sub.done:
        _maybe_auto_complete_parent(session, sub.task_id)
        # parent may have changed; re-load sub for fresh session state
        session.refresh(sub)
    return sub


def delete_subtask(session: Session, subtask_id: int) -> bool:
    sub = session.get(Subtask, subtask_id)
    if not sub:
        return False
    session.delete(sub)
    session.commit()
    return True


def move_subtask(session: Session, subtask_id: int, direction: int) -> Optional[Subtask]:
    """Swap position with neighbor. direction: -1 up, +1 down."""
    sub = session.get(Subtask, subtask_id)
    if not sub or direction not in (-1, 1):
        return None
    items = list_subtasks(session, sub.task_id)
    idx = next((i for i, s in enumerate(items) if s.id == sub.id), None)
    if idx is None:
        return None
    j = idx + direction
    if j < 0 or j >= len(items):
        return sub
    items[idx], items[j] = items[j], items[idx]
    for i, s in enumerate(items):
        s.position = i
    session.commit()
    session.refresh(sub)
    return sub

