"""Global search across tasks and goals by title; recent query history in app_meta."""
from __future__ import annotations

import json
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_meta, set_meta
from app.models import Goal, Task
from app.schemas import SearchResult

RECENT_SEARCHES_KEY = "recent_searches"
RECENT_SEARCHES_MAX = 5


def search(session: Session, query: str, *, limit: int = 40) -> SearchResult:
    """Find tasks + goals whose title matches ``query`` (case-insensitive).

    Returns ``{"tasks": [...], "goals": [...], "query": str}``.
    Empty / whitespace query → empty lists.
    """
    q = (query or "").strip()
    if not q:
        return {"tasks": [], "goals": [], "query": ""}
    like = f"%{q}%"
    tasks = list(
        session.scalars(
            select(Task)
            .options(selectinload(Task.subtasks))
            .where(Task.title.ilike(like))
            .order_by(Task.created_at.desc())
            .limit(limit)
        )
        .unique()
        .all()
    )
    goals = list(
        session.scalars(
            select(Goal)
            .where(Goal.title.ilike(like))
            .order_by(Goal.created_at.desc())
            .limit(limit)
        ).all()
    )
    return {"tasks": tasks, "goals": goals, "query": q}


def get_recent_searches(session: Session) -> list[str]:
    """Last up to 5 search queries from app_meta JSON. Safe on missing/corrupt."""
    raw = get_meta(session, RECENT_SEARCHES_KEY)
    if raw is None or str(raw).strip() == "":
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, str):
            continue
        q = item.strip()
        if not q:
            continue
        key = q.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(q)
        if len(out) >= RECENT_SEARCHES_MAX:
            break
    return out


def remember_search(session: Session, query: str) -> list[str]:
    """Prepend ``query`` to recent searches (dedupe, max 5). Commits meta.

    Empty / whitespace ignored. Corrupt meta is replaced. Returns new list.
    """
    q = (query or "").strip()
    if not q:
        return get_recent_searches(session)
    prev = get_recent_searches(session)
    # drop case-insensitive duplicates of q
    key = q.casefold()
    rest = [x for x in prev if x.casefold() != key]
    updated = [q] + rest
    updated = updated[:RECENT_SEARCHES_MAX]
    try:
        set_meta(session, RECENT_SEARCHES_KEY, json.dumps(updated, ensure_ascii=False))
        session.commit()
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
        return get_recent_searches(session)
    return updated


def clear_recent_searches(session: Session) -> None:
    """Clear recent search history (tests)."""
    try:
        set_meta(session, RECENT_SEARCHES_KEY, "[]")
        session.commit()
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
