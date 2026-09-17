"""In-app reminder center — due today, overdue, incomplete goal quotas."""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.services import goal_service, task_service


def list_reminders(session: Session, *, today: date | None = None) -> dict[str, Any]:
    """Return reminder buckets for the in-app center."""
    today = today or date.today()
    due_today = task_service.list_tasks(session, due_today=True, archived=False)
    overdue = task_service.list_tasks(session, overdue=True, archived=False)
    incomplete_goals = [
        q for q in goal_service.today_quotas(session) if not q.get("complete")
    ]
    return {
        "due_today": due_today,
        "overdue": overdue,
        "incomplete_goals": incomplete_goals,
        "count": len(due_today) + len(overdue) + len(incomplete_goals),
    }
