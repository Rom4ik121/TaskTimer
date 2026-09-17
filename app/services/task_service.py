"""Task CRUD service — single write path with completed_at / archive / recur handling."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import RoadmapNode, Subtask, Task, TimeSession
from app.schemas import TaskCreate, TaskUpdate, WeekDueSummary


def is_overdue(task: Task, *, today: date | None = None) -> bool:
    today = today or date.today()
    if getattr(task, "archived", False):
        return False
    return (
        task.status != "done"
        and task.due_date is not None
        and task.due_date < today
    )


def is_due_today(task: Task, *, today: date | None = None) -> bool:
    today = today or date.today()
    if getattr(task, "archived", False):
        return False
    return (
        task.status != "done"
        and task.due_date is not None
        and task.due_date == today
    )


def is_due_tomorrow(task: Task, *, today: date | None = None) -> bool:
    today = today or date.today()
    if getattr(task, "archived", False):
        return False
    return (
        task.status != "done"
        and task.due_date is not None
        and task.due_date == today + timedelta(days=1)
    )


def format_due_label(task: Task, *, today: date | None = None) -> tuple[str, str]:
    """Return (label, kind) where kind is overdue|today|soon|normal|none.

    Labels are Russian relative when close to today.
    """
    today = today or date.today()
    if task.due_date is None:
        return "без срока", "none"
    d = task.due_date
    delta = (d - today).days
    if getattr(task, "archived", False):
        return d.isoformat(), "normal"
    if task.status != "done" and delta < 0:
        days = -delta
        if days == 1:
            return "вчера", "overdue"
        return f"просрочено · {days} дн", "overdue"
    if delta == 0:
        return "сегодня", "today"
    if delta == 1:
        return "завтра", "soon"
    if delta <= 7:
        return f"через {delta} дн", "soon"
    return d.isoformat(), "normal"


def list_color_tags(session: Session, *, archived: bool = False) -> list[str]:
    """Distinct non-empty color tags among non-done-filtered active/archive tasks."""
    stmt = select(Task.color_tag).where(Task.color_tag.is_not(None)).where(Task.color_tag != "")
    if archived:
        stmt = stmt.where(Task.archived.is_(True))
    else:
        stmt = stmt.where(Task.archived.is_(False))
    tags = sorted({t for t in session.scalars(stmt).all() if t})
    return tags


def week_due_summary(session: Session, *, today: date | None = None, week_starts_monday: bool = True) -> WeekDueSummary:
    """Tasks due in the current calendar week (Mon–Sun or Sun–Sat)."""
    today = today or date.today()
    if week_starts_monday:
        start = today - timedelta(days=today.weekday())
    else:
        # Sunday start
        start = today - timedelta(days=(today.weekday() + 1) % 7)
    end = start + timedelta(days=6)
    tasks = list_tasks(session, archived=False)
    due = [
        t
        for t in tasks
        if t.status != "done" and t.due_date is not None and start <= t.due_date <= end
    ]
    overdue_n = sum(1 for t in due if is_overdue(t, today=today))
    today_n = sum(1 for t in due if is_due_today(t, today=today))
    return {
        "start": start,
        "end": end,
        "tasks": due,
        "count": len(due),
        "overdue": overdue_n,
        "due_today": today_n,
    }



def next_recur_due(
    rule: str,
    *,
    base: date | None = None,
    today: date | None = None,
) -> date:
    """Shift due date for the next occurrence (daily / weekly)."""
    today = today or date.today()
    cur = base or today
    if rule == "weekly":
        nxt = cur + timedelta(days=7)
        while nxt <= today:
            nxt += timedelta(days=7)
        return nxt
    # daily (default for any non-none)
    nxt = cur + timedelta(days=1)
    if nxt <= today:
        nxt = today + timedelta(days=1)
    return nxt


def _copy_open_subtasks(session: Session, source: Task, target: Task) -> int:
    """Copy undone checklist items onto the newly spawned recurring task."""
    open_subs = session.scalars(
        select(Subtask)
        .where(Subtask.task_id == source.id)
        .where(Subtask.done.is_(False))
        .order_by(Subtask.position.asc(), Subtask.id.asc())
    ).all()
    for i, sub in enumerate(open_subs):
        session.add(
            Subtask(
                task_id=target.id,
                title=sub.title,
                done=False,
                position=i,
            )
        )
    if open_subs:
        session.flush()
    return len(open_subs)


def _archive_on_recur_enabled(session: Session) -> bool:
    from app.db import get_meta

    raw = get_meta(session, "archive_on_recur_done")
    if raw is None:
        return False
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _spawn_next_occurrence(session: Session, task: Task) -> Optional[Task]:
    """Create the next todo from a recurring task that just became done."""
    rule = (getattr(task, "recur_rule", None) or "none").strip().lower()
    if rule not in ("daily", "weekly"):
        return None
    today = date.today()
    next_due = next_recur_due(rule, base=task.due_date, today=today)
    anchor = getattr(task, "recur_anchor", None) or task.due_date or today
    base_desc = (task.description or "").strip()
    # Strip prior spawn notes from description copy
    lines = [
        ln
        for ln in base_desc.splitlines()
        if "из повтора" not in ln.lower()
    ]
    clean = "\n".join(lines).strip()
    note = f"— из повтора #{task.id}"
    description = f"{clean}\n{note}".strip() if clean else note
    child = Task(
        title=task.title,
        description=description,
        status="todo",
        priority=task.priority or "medium",
        due_date=next_due,
        goal_id=task.goal_id,
        color_tag=task.color_tag,
        pinned=bool(getattr(task, "pinned", False)),
        archived=False,
        recur_rule=rule,
        recur_anchor=anchor,
        estimated_min=getattr(task, "estimated_min", None),
        inbox=False,
        completed_at=None,
    )
    session.add(child)
    session.flush()
    _copy_open_subtasks(session, task, child)
    return child


def list_tasks(
    session: Session,
    status: Optional[str] = None,
    *,
    query: Optional[str] = None,
    overdue: bool = False,
    archived: Optional[bool] = False,
    due_today: bool = False,
    priority: Optional[str] = None,
    color_tag: Optional[str] = None,
    pinned: Optional[bool] = None,
    inbox: Optional[bool] = None,
    sort: Optional[str] = None,
) -> list[Task]:
    """List tasks.

    ``archived``:
      - False (default): hide archived
      - True: only archived
      - None: include both

    ``sort``: ``due`` | ``priority`` | ``created`` | None.
    When None and no status/overdue/due_today filter: pinned first, then overdue,
    then due today, then others; within each group ``created_at`` desc.
    """
    stmt = (
        select(Task)
        .options(selectinload(Task.subtasks))
        .order_by(Task.created_at.desc())
    )
    if archived is True:
        stmt = stmt.where(Task.archived.is_(True))
    elif archived is False:
        stmt = stmt.where(Task.archived.is_(False))
    if status:
        stmt = stmt.where(Task.status == status)
    if priority:
        stmt = stmt.where(Task.priority == priority)
    if color_tag:
        stmt = stmt.where(Task.color_tag == color_tag)
    if pinned is True:
        stmt = stmt.where(Task.pinned.is_(True))
    elif pinned is False:
        stmt = stmt.where(Task.pinned.is_(False))
    if inbox is True:
        # Inbox chip: only inbox & not archived
        stmt = stmt.where(Task.inbox.is_(True)).where(Task.archived.is_(False))
    elif inbox is False:
        stmt = stmt.where(Task.inbox.is_(False))
    if overdue:
        stmt = (
            stmt.where(Task.status != "done")
            .where(Task.due_date.is_not(None))
            .where(Task.due_date < date.today())
        )
    if due_today:
        stmt = (
            stmt.where(Task.status != "done")
            .where(Task.due_date.is_not(None))
            .where(Task.due_date == date.today())
        )
    if query:
        q = f"%{query.strip()}%"
        stmt = stmt.where(
            or_(Task.title.ilike(q), Task.description.ilike(q), Task.color_tag.ilike(q))
        )
    tasks = list(session.scalars(stmt).unique().all())
    sort_key = (sort or "").strip().lower() or None
    _pri_rank = {"high": 0, "medium": 1, "low": 2}
    def _pin_rank(t: Task) -> int:
        return 0 if getattr(t, "pinned", False) else 1

    if sort_key == "due":
        tasks.sort(
            key=lambda t: (
                _pin_rank(t),
                0 if t.due_date is not None else 1,
                t.due_date.toordinal() if t.due_date else 0,
                -(t.created_at.timestamp() if t.created_at else 0.0),
            )
        )
    elif sort_key == "priority":
        tasks.sort(
            key=lambda t: (
                _pin_rank(t),
                _pri_rank.get(t.priority or "medium", 9),
                -(t.created_at.timestamp() if t.created_at else 0.0),
            )
        )
    elif sort_key == "created":
        tasks.sort(
            key=lambda t: (
                _pin_rank(t),
                -(t.created_at.timestamp() if t.created_at else 0.0),
            )
        )
    elif not status and not overdue and not due_today:
        today = date.today()

        def _bucket(t: Task) -> int:
            if is_overdue(t, today=today):
                return 0
            if is_due_today(t, today=today):
                return 1
            return 2

        tasks.sort(
            key=lambda t: (
                0 if getattr(t, "pinned", False) else 1,
                _bucket(t),
                -(t.created_at.timestamp() if t.created_at else 0.0),
            )
        )
    else:
        # Keep pinned on top for filtered lists too (except pure archive)
        if archived is not True:
            tasks.sort(
                key=lambda t: (
                    0 if getattr(t, "pinned", False) else 1,
                    -(t.created_at.timestamp() if t.created_at else 0.0),
                )
            )
    return tasks


def get_task(session: Session, task_id: int) -> Optional[Task]:
    return session.get(Task, task_id)


def _apply_status_side_effects(session: Session, task: Task, new_status: str) -> None:
    if new_status == "done" and task.status != "done":
        from app.db import set_meta

        prev = task.status if task.status in ("todo", "in_progress") else "todo"
        set_meta(session, "last_completed_task_id", str(task.id))
        set_meta(session, "last_completed_prev_status", prev)
        task.completed_at = datetime.now()
        child = _spawn_next_occurrence(session, task)
        if child is not None and _archive_on_recur_enabled(session):
            task.archived = True
    elif new_status != "done":
        task.completed_at = None


def create_task(session: Session, data: TaskCreate) -> Task:
    payload = data.model_dump()
    rule = (payload.get("recur_rule") or "none").strip().lower()
    if rule not in ("none", "daily", "weekly"):
        rule = "none"
    payload["recur_rule"] = rule
    if rule != "none" and not payload.get("recur_anchor"):
        payload["recur_anchor"] = payload.get("due_date") or date.today()
    if rule == "none":
        payload["recur_anchor"] = payload.get("recur_anchor")  # may stay None
    task = Task(**payload)
    if task.status == "done":
        task.completed_at = datetime.now()
    session.add(task)
    session.flush()
    if task.status == "done":
        child = _spawn_next_occurrence(session, task)
        if child is not None and _archive_on_recur_enabled(session):
            task.archived = True
    session.commit()
    session.refresh(task)
    return task


def update_task(session: Session, task_id: int, data: TaskUpdate) -> Optional[Task]:
    task = session.get(Task, task_id)
    if not task:
        return None
    updates = data.model_dump(exclude_unset=True)
    if "recur_rule" in updates:
        rule = (updates["recur_rule"] or "none").strip().lower()
        if rule not in ("none", "daily", "weekly"):
            rule = "none"
        updates["recur_rule"] = rule
        if rule != "none" and not updates.get("recur_anchor") and not task.recur_anchor:
            updates.setdefault(
                "recur_anchor",
                updates.get("due_date") or task.due_date or date.today(),
            )
    # Apply non-status fields first so recur_* is current when spawning
    pending_status = updates.pop("status", None)
    meaningful = {
        "title",
        "description",
        "priority",
        "due_date",
        "goal_id",
        "color_tag",
        "recur_rule",
        "estimated_min",
        "pinned",
    }
    explicit_inbox = "inbox" in updates
    for key, value in updates.items():
        setattr(task, key, value)
    if pending_status is not None:
        _apply_status_side_effects(session, task, pending_status)
        task.status = pending_status
    # Promote out of inbox on meaningful edit (unless inbox explicitly set)
    if getattr(task, "inbox", False) and not explicit_inbox:
        if pending_status is not None or (updates.keys() & meaningful):
            task.inbox = False
    session.commit()
    session.refresh(task)
    return task


def delete_task(session: Session, task_id: int) -> bool:
    task = session.get(Task, task_id)
    if not task:
        return False
    for node in session.scalars(
        select(RoadmapNode).where(RoadmapNode.task_id == task_id)
    ).all():
        node.task_id = None
    for tsess in session.scalars(
        select(TimeSession).where(TimeSession.task_id == task_id)
    ).all():
        tsess.task_id = None
    for sub in session.scalars(
        select(Subtask).where(Subtask.task_id == task_id)
    ).all():
        session.delete(sub)
    session.delete(task)
    session.commit()
    return True


def set_status(session: Session, task_id: int, status: str) -> Optional[Task]:
    return update_task(session, task_id, TaskUpdate(status=status))  # type: ignore[arg-type]


def archive_task(session: Session, task_id: int) -> Optional[Task]:
    return update_task(session, task_id, TaskUpdate(archived=True))


def unarchive_task(session: Session, task_id: int) -> Optional[Task]:
    return update_task(session, task_id, TaskUpdate(archived=False))



def archive_tasks(session: Session, task_ids: list[int]) -> int:
    """Archive many tasks in one commit. Returns how many were newly archived."""
    n = 0
    seen: set[int] = set()
    for tid in task_ids:
        if tid in seen:
            continue
        seen.add(tid)
        task = session.get(Task, tid)
        if not task or getattr(task, "archived", False):
            continue
        task.archived = True
        n += 1
    if n:
        session.commit()
    return n


def set_pinned(session: Session, task_id: int, pinned: bool) -> Optional[Task]:
    return update_task(session, task_id, TaskUpdate(pinned=bool(pinned)))


def duplicate_task(session: Session, task_id: int) -> Optional[Task]:
    """Clone title/desc/priority/goal/undone subtasks/recur/color; status todo.

    Does not copy pinned/archived/completed_at. Due date is copied when set.
    """
    source = session.get(Task, task_id)
    if not source:
        return None
    rule = (getattr(source, "recur_rule", None) or "none").strip().lower()
    if rule not in ("none", "daily", "weekly"):
        rule = "none"
    child = Task(
        title=source.title,
        description=source.description or "",
        status="todo",
        priority=source.priority or "medium",
        due_date=source.due_date,
        goal_id=source.goal_id,
        color_tag=source.color_tag,
        pinned=False,
        archived=False,
        recur_rule=rule,
        recur_anchor=getattr(source, "recur_anchor", None),
        estimated_min=getattr(source, "estimated_min", None),
        inbox=False,
        completed_at=None,
    )
    session.add(child)
    session.flush()
    _copy_open_subtasks(session, source, child)
    session.commit()
    session.refresh(child)
    return child



def complete_tasks(session: Session, task_ids: list[int]) -> int:
    """Mark many tasks done (triggers recur spawn). Returns how many flipped to done."""
    n = 0
    seen: set[int] = set()
    for tid in task_ids:
        if tid in seen:
            continue
        seen.add(tid)
        task = session.get(Task, tid)
        if not task or task.status == "done":
            continue
        _apply_status_side_effects(session, task, "done")
        task.status = "done"
        n += 1
    if n:
        session.commit()
    return n


def clear_done_tasks(session: Session, *, archive: bool = True) -> int:
    """Archive (default) or delete all done non-archived tasks. Returns count."""
    tasks = list(
        session.scalars(
            select(Task).where(Task.status == "done").where(Task.archived.is_(False))
        ).all()
    )
    if not tasks:
        return 0
    if archive:
        for t in tasks:
            t.archived = True
        session.commit()
        return len(tasks)
    ids = [t.id for t in tasks]
    n = 0
    for tid in ids:
        if delete_task(session, tid):
            n += 1
    return n




def quick_capture(session: Session, title: str) -> Task:
    """Create a medium-priority todo in the inbox. Raises ValueError on empty title."""
    cleaned = (title or "").strip()
    if not cleaned:
        raise ValueError("title required")
    return create_task(
        session,
        TaskCreate(title=cleaned, status="todo", priority="medium", inbox=True),
    )


def set_inbox(session: Session, task_id: int, inbox: bool) -> Optional[Task]:
    """Explicitly set / clear inbox flag."""
    return update_task(session, task_id, TaskUpdate(inbox=bool(inbox)))


def promote_from_inbox(session: Session, task_id: int) -> Optional[Task]:
    """Clear inbox flag (promote to regular task list)."""
    return set_inbox(session, task_id, False)


def undo_last_complete(session: Session) -> Optional[Task]:
    """Restore the last completed task to its previous status; clear undo meta.

    Returns None if meta missing, task gone, archived, or not currently done.
    """
    from app.db import get_meta, set_meta

    raw_id = get_meta(session, "last_completed_task_id")
    raw_prev = get_meta(session, "last_completed_prev_status")
    if not raw_id:
        return None
    try:
        tid = int(str(raw_id).strip())
    except (TypeError, ValueError):
        return None
    prev = (raw_prev or "todo").strip().lower()
    if prev not in ("todo", "in_progress"):
        prev = "todo"
    task = session.get(Task, tid)
    if not task or getattr(task, "archived", False) or task.status != "done":
        set_meta(session, "last_completed_task_id", "")
        set_meta(session, "last_completed_prev_status", "")
        session.commit()
        return None
    task.status = prev
    task.completed_at = None
    set_meta(session, "last_completed_task_id", "")
    set_meta(session, "last_completed_prev_status", "")
    session.commit()
    session.refresh(task)
    return task


def today_estimate_minutes(session: Session, *, today: date | None = None) -> int:
    """Sum of estimated_min for open (non-archived, not-done) overdue + due-today tasks.

    Only overdue and due_today are included — a clear «сегодня» workload estimate.
    Tasks without estimated_min are skipped.
    """
    today = today or date.today()
    total = 0
    for t in list_tasks(session, archived=False):
        if t.status == "done":
            continue
        em = getattr(t, "estimated_min", None)
        if em is None:
            continue
        try:
            mins = int(em)
        except (TypeError, ValueError):
            continue
        if mins <= 0:
            continue
        if is_overdue(t, today=today) or is_due_today(t, today=today):
            total += mins
    return total


def snooze_due(session: Session, task_id: int, days: int = 1) -> Optional[Task]:
    """Push due_date forward by ``days`` (default 1). Never archives.

    If the task has no due_date, set it to today + days.
    """
    task = session.get(Task, task_id)
    if not task:
        return None
    days = max(0, int(days))
    today = date.today()
    if task.due_date is None:
        task.due_date = today + timedelta(days=days)
    else:
        task.due_date = task.due_date + timedelta(days=days)
    session.commit()
    session.refresh(task)
    return task


def snooze_all_overdue(session: Session, *, days: int = 1, today: date | None = None) -> int:
    """Snooze every overdue (non-archived, not done) task by ``days``. Returns count."""
    today = today or date.today()
    days = max(1, int(days))
    n = 0
    for t in list_tasks(session, archived=False):
        if not is_overdue(t, today=today):
            continue
        if t.due_date is None:
            continue
        t.due_date = t.due_date + timedelta(days=days)
        n += 1
    if n:
        session.commit()
    return n

