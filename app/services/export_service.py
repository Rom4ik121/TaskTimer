"""Export / import backup helpers."""
from __future__ import annotations

import csv
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import get_db_path, get_meta, set_meta
from app.models import (
    CanvasEdge,
    CanvasNode,
    Goal,
    ProgressLog,
    RoadmapEdge,
    RoadmapNode,
    Subtask,
    Task,
    TimeSession,
)
from app.services import notes_service, settings_service
from app.schemas import SettingsUpdate


LAST_IMPORT_BACKUP_KEY = "last_import_backup"
LAST_EXPORT_PATH_KEY = "last_export_path"
LAST_EXPORT_AT_KEY = "last_export_at"


def get_last_import_backup(session: Session) -> Path | None:
    """Return path to pre-replace backup if meta points to an existing file."""
    raw = get_meta(session, LAST_IMPORT_BACKUP_KEY)
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_file() else None


def clear_last_import_backup(session: Session) -> None:
    set_meta(session, LAST_IMPORT_BACKUP_KEY, "")

def record_last_export(session: Session, path: Path | str) -> None:
    """Persist last successful export path + timestamp in app_meta."""
    p = Path(path)
    set_meta(session, LAST_EXPORT_PATH_KEY, str(p.resolve() if p.is_absolute() else p))
    set_meta(
        session,
        LAST_EXPORT_AT_KEY,
        datetime.now().isoformat(timespec="seconds"),
    )
    session.flush()


def get_last_export(session: Session) -> tuple[str | None, str | None]:
    """Return (path, iso_time) from app_meta; either may be None."""
    return get_meta(session, LAST_EXPORT_PATH_KEY), get_meta(session, LAST_EXPORT_AT_KEY)


BACKUP_TIP_DISMISS_KEY = "backup_tip_dismissed"


def _as_today(today: date | datetime | str | None) -> date:
    """Normalize today arg; never raise — fall back to ``date.today()``."""
    if today is None:
        return date.today()
    if isinstance(today, datetime):
        return today.date()
    if isinstance(today, date):
        return today
    raw = str(today).strip()
    if not raw:
        return date.today()
    try:
        return date.fromisoformat(raw[:10])
    except (TypeError, ValueError):
        return date.today()


def _parse_dismiss_day(raw: str | None) -> date | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s.lower() in ("1", "0", "true", "false", "yes", "no", "on", "off"):
        return None
    try:
        return date.fromisoformat(s[:10])
    except (TypeError, ValueError):
        return None


def is_backup_tip_dismissed(
    session: Session, *, today: date | datetime | str | None = None
) -> bool:
    """True when Home backup tip was dismissed for ``today`` (ISO date in meta)."""
    day = _as_today(today)
    try:
        raw = get_meta(session, BACKUP_TIP_DISMISS_KEY)
    except Exception:
        return False
    stored = _parse_dismiss_day(raw)
    if stored is None:
        return False
    return stored == day


def dismiss_backup_tip(
    session: Session, *, today: date | datetime | str | None = None
) -> None:
    """Hide backup tip for the rest of today. Idempotent."""
    day = _as_today(today)
    iso = day.isoformat()
    try:
        raw = get_meta(session, BACKUP_TIP_DISMISS_KEY)
        if str(raw or "").strip() == iso:
            return
        set_meta(session, BACKUP_TIP_DISMISS_KEY, iso)
        session.commit()
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass


def clear_backup_tip_dismiss(session: Session) -> None:
    """Clear dismiss flag so the tip can show again (tests / day rollover)."""
    try:
        set_meta(session, BACKUP_TIP_DISMISS_KEY, "")
        session.commit()
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass


def needs_backup_reminder(session: Session, *, days: int = 7) -> bool:
    """True if last_export_at is missing or older than ``days`` calendar days.

    Parses ISO timestamps from ``record_last_export``; corrupt/empty meta → remind.
    """
    _, at_raw = get_last_export(session)
    if not at_raw or not str(at_raw).strip():
        return True
    raw = str(at_raw).strip()
    try:
        # Accept full ISO or date-only prefix
        if "T" in raw:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            last = dt.date()
        else:
            last = date.fromisoformat(raw[:10])
    except (TypeError, ValueError):
        return True
    age = (date.today() - last).days
    return age >= int(days)



def write_pre_import_backup(session: Session, dest_dir: Path | None = None) -> Path:
    """Snapshot current DB before a replace-import; store path in app_meta."""
    folder = dest_dir or (get_db_path().parent)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = folder / f"pre-import-{stamp}.json"
    data = export_all(session)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    set_meta(session, LAST_IMPORT_BACKUP_KEY, str(path.resolve()))
    session.flush()
    return path


def undo_last_replace_import(session: Session) -> dict:
    """Restore from last pre-import backup (replace). Clears undo meta after success."""
    path = get_last_import_backup(session)
    if path is None:
        raise FileNotFoundError("Нет бэкапа для отмены импорта")
    path_str = str(path)
    # Import without creating another pre-import backup
    summary = import_all(session, path, mode="replace", backup_before_replace=False)
    # import_all commits; clear undo pointer in a follow-up write
    clear_last_import_backup(session)
    session.commit()
    summary["undone_from"] = path_str
    return summary

def _ser(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return obj


def _parse_dt(val: Any) -> datetime | None:
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val
    s = str(val)
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _parse_date(val: Any) -> date | None:
    if val is None or val == "":
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    s = str(val)[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None



def _export_notes_vault() -> dict[str, str]:
    """Serialize vault ``*.md`` contents keyed by safe basename."""
    out: dict[str, str] = {}
    try:
        notes_service.ensure_vault()
        for name in notes_service.list_notes():
            try:
                safe = notes_service.sanitize_filename(name)
                out[safe] = notes_service.read_note(safe)
            except (ValueError, OSError):
                continue
    except OSError:
        pass
    return out


def _export_canvas(session: Session) -> tuple[list[dict], list[dict]]:
    nodes = [
        {
            "id": n.id,
            "title": n.title,
            "x": n.x,
            "y": n.y,
            "kind": n.kind,
            "ref": n.ref,
            "color": n.color,
            "w": n.w,
            "h": n.h,
        }
        for n in session.scalars(select(CanvasNode).order_by(CanvasNode.id)).all()
    ]
    edges = [
        {
            "id": e.id,
            "from_node_id": e.from_node_id,
            "to_node_id": e.to_node_id,
        }
        for e in session.scalars(select(CanvasEdge).order_by(CanvasEdge.id)).all()
    ]
    return nodes, edges


def _import_notes_vault(notes: Any, *, counts: dict) -> None:
    """Restore vault files via sanitize/path confinement. Skips unsafe names."""
    if not isinstance(notes, dict):
        return
    try:
        notes_service.ensure_vault()
    except OSError:
        return
    n_ok = 0
    for raw_name, body in notes.items():
        try:
            safe = notes_service.sanitize_filename(str(raw_name))
        except ValueError:
            continue
        try:
            notes_service.write_note(safe, "" if body is None else str(body))
            n_ok += 1
        except (ValueError, OSError):
            continue
    counts["notes"] = n_ok


def export_all(session: Session) -> dict:
    """Serialize full app state to a JSON-friendly dict."""
    settings = settings_service.get_settings(session)
    tasks = []
    for t in session.scalars(select(Task).order_by(Task.id)).all():
        tasks.append(
            {
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "status": t.status,
                "priority": t.priority,
                "due_date": _ser(t.due_date),
                "goal_id": t.goal_id,
                "color_tag": t.color_tag,
                "pinned": bool(getattr(t, "pinned", False)),
                "archived": bool(getattr(t, "archived", False)),
                "recur_rule": getattr(t, "recur_rule", None) or "none",
                "recur_anchor": _ser(getattr(t, "recur_anchor", None)),
                "estimated_min": getattr(t, "estimated_min", None),
                "inbox": bool(getattr(t, "inbox", False)),
                "completed_at": _ser(t.completed_at),
                "created_at": _ser(t.created_at),
            }
        )
    subtasks = [
        {
            "id": s.id,
            "task_id": s.task_id,
            "title": s.title,
            "done": bool(s.done),
            "position": s.position,
        }
        for s in session.scalars(select(Subtask).order_by(Subtask.id)).all()
    ]
    goals = [
        {
            "id": g.id,
            "title": g.title,
            "description": g.description,
            "target_value": g.target_value,
            "unit": g.unit,
            "daily_quota": g.daily_quota,
            "current_value": g.current_value,
            "archived": bool(getattr(g, "archived", False)),
            "created_at": _ser(g.created_at),
        }
        for g in session.scalars(select(Goal).order_by(Goal.id)).all()
    ]
    logs = [
        {
            "id": lg.id,
            "goal_id": lg.goal_id,
            "amount": lg.amount,
            "note": lg.note,
            "logged_at": _ser(lg.logged_at),
        }
        for lg in session.scalars(select(ProgressLog).order_by(ProgressLog.id)).all()
    ]
    nodes = [
        {
            "id": n.id,
            "title": n.title,
            "x": n.x,
            "y": n.y,
            "status": n.status,
            "task_id": n.task_id,
        }
        for n in session.scalars(select(RoadmapNode).order_by(RoadmapNode.id)).all()
    ]
    edges = [
        {
            "id": e.id,
            "from_node_id": e.from_node_id,
            "to_node_id": e.to_node_id,
        }
        for e in session.scalars(select(RoadmapEdge).order_by(RoadmapEdge.id)).all()
    ]
    sessions = [
        {
            "id": ts.id,
            "task_id": ts.task_id,
            "label": ts.label,
            "duration_sec": ts.duration_sec,
            "remaining_sec": ts.remaining_sec,
            "status": ts.status,
            "note": getattr(ts, "note", None) or "",
            "started_at": _ser(ts.started_at),
            "created_at": _ser(ts.created_at),
        }
        for ts in session.scalars(select(TimeSession).order_by(TimeSession.id)).all()
    ]
    canvas_nodes, canvas_edges = _export_canvas(session)
    return {
        "format": "tasktimer-export",
        "version": 2,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "schema_version": get_meta(session, "schema_version"),
        "settings": settings.model_dump(),
        "goals": goals,
        "tasks": tasks,
        "subtasks": subtasks,
        "progress_logs": logs,
        "roadmap_nodes": nodes,
        "roadmap_edges": edges,
        "time_sessions": sessions,
        "notes": _export_notes_vault(),
        "canvas_nodes": canvas_nodes,
        "canvas_edges": canvas_edges,
    }


def write_export_file(session: Session, dest_dir: Path | None = None) -> Path:
    """Write export JSON under data/ and return path."""
    data = export_all(session)
    folder = dest_dir or (get_db_path().parent)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = folder / f"export-{stamp}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    record_last_export(session, path)
    session.commit()
    return path


def load_export_payload(source: Path | str | dict) -> dict:
    """Load and lightly validate export JSON from path or dict."""
    if isinstance(source, dict):
        data = source
    else:
        path = Path(source)
        data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("export must be a JSON object")
    fmt = data.get("format")
    if fmt and fmt != "tasktimer-export":
        raise ValueError(f"unknown format: {fmt}")
    return data


def is_content_empty(session: Session) -> bool:
    """True when no tasks and no goals."""
    return _content_empty(session)


def _content_empty(session: Session) -> bool:
    n_tasks = session.scalar(select(Task.id).limit(1))
    n_goals = session.scalar(select(Goal.id).limit(1))
    return n_tasks is None and n_goals is None


def _clear_all(session: Session) -> None:
    session.execute(delete(CanvasEdge))
    session.execute(delete(CanvasNode))
    session.execute(delete(RoadmapEdge))
    session.execute(delete(RoadmapNode))
    session.execute(delete(TimeSession))
    session.execute(delete(Subtask))
    session.execute(delete(ProgressLog))
    session.execute(delete(Task))
    session.execute(delete(Goal))
    session.flush()


def _apply_settings(session: Session, settings: dict | None) -> None:
    if not settings or not isinstance(settings, dict):
        return
    payload: dict[str, Any] = {}
    if "display_name" in settings and settings["display_name"]:
        payload["display_name"] = str(settings["display_name"])
    if "accent_hex" in settings and settings["accent_hex"]:
        payload["accent_hex"] = str(settings["accent_hex"])
    if "week_starts_monday" in settings and settings["week_starts_monday"] is not None:
        payload["week_starts_monday"] = bool(settings["week_starts_monday"])
    if "pomodoro_work_min" in settings and settings["pomodoro_work_min"] is not None:
        try:
            payload["pomodoro_work_min"] = int(settings["pomodoro_work_min"])
        except (TypeError, ValueError):
            pass
    if "pomodoro_break_min" in settings and settings["pomodoro_break_min"] is not None:
        try:
            payload["pomodoro_break_min"] = int(settings["pomodoro_break_min"])
        except (TypeError, ValueError):
            pass
    if "archive_on_recur_done" in settings and settings["archive_on_recur_done"] is not None:
        payload["archive_on_recur_done"] = bool(settings["archive_on_recur_done"])
    if "quiet_start" in settings and settings["quiet_start"] is not None:
        try:
            payload["quiet_start"] = int(settings["quiet_start"])
        except (TypeError, ValueError):
            pass
    if "quiet_end" in settings and settings["quiet_end"] is not None:
        try:
            payload["quiet_end"] = int(settings["quiet_end"])
        except (TypeError, ValueError):
            pass
    if "auto_complete_subtasks" in settings and settings["auto_complete_subtasks"] is not None:
        payload["auto_complete_subtasks"] = bool(settings["auto_complete_subtasks"])
    if "compact_ui" in settings and settings["compact_ui"] is not None:
        payload["compact_ui"] = bool(settings["compact_ui"])
    if "wind_down_hour" in settings and settings["wind_down_hour"] is not None:
        try:
            payload["wind_down_hour"] = int(settings["wind_down_hour"])
        except (TypeError, ValueError):
            pass
    if "weekly_task_target" in settings and settings["weekly_task_target"] is not None:
        try:
            payload["weekly_task_target"] = int(settings["weekly_task_target"])
        except (TypeError, ValueError):
            pass
    if payload:
        settings_service.update_settings(session, SettingsUpdate(**payload))


def import_all(
    session: Session,
    source: Path | str | dict,
    *,
    mode: Literal["merge", "replace"] | None = None,
    backup_before_replace: bool = True,
) -> dict:
    """Import backup JSON.

    Default mode is confirm-safe: ``replace`` into an empty DB, otherwise ``merge``
    by title (goals/tasks). Returns a summary dict.

    When ``mode=="replace"`` and the DB has content, a pre-import snapshot is
    written and its path stored in ``app_meta.last_import_backup`` (soft undo)
    unless ``backup_before_replace`` is False.
    """
    data = load_export_payload(source)
    if mode is None:
        mode = "replace" if _content_empty(session) else "merge"
    if mode not in ("merge", "replace"):
        raise ValueError("mode must be merge or replace")

    goal_map: dict[int, int] = {}
    task_map: dict[int, int] = {}
    node_map: dict[int, int] = {}
    counts = {
        "mode": mode,
        "goals": 0,
        "tasks": 0,
        "subtasks": 0,
        "progress_logs": 0,
        "roadmap_nodes": 0,
        "roadmap_edges": 0,
        "time_sessions": 0,
        "notes": 0,
        "canvas_nodes": 0,
        "canvas_edges": 0,
        "merged_goals": 0,
        "merged_tasks": 0,
        "pre_import_backup": None,
    }

    if mode == "replace":
        if backup_before_replace and not _content_empty(session):
            try:
                bak = write_pre_import_backup(session)
                counts["pre_import_backup"] = str(bak)
            except Exception:
                counts["pre_import_backup"] = None
        _clear_all(session)

    # Index existing by title for merge
    existing_goals: dict[str, Goal] = {}
    existing_tasks: dict[str, Task] = {}
    if mode == "merge":
        for g in session.scalars(select(Goal)).all():
            existing_goals[g.title.strip().lower()] = g
        for t in session.scalars(select(Task)).all():
            existing_tasks[t.title.strip().lower()] = t

    for g in data.get("goals") or []:
        old_id = g.get("id")
        title = (g.get("title") or "Цель").strip()
        key = title.lower()
        if mode == "merge" and key in existing_goals:
            goal = existing_goals[key]
            goal.description = g.get("description") or goal.description
            if g.get("target_value"):
                goal.target_value = float(g["target_value"])
            if g.get("unit"):
                goal.unit = str(g["unit"])
            if g.get("daily_quota"):
                goal.daily_quota = float(g["daily_quota"])
            if g.get("current_value") is not None:
                goal.current_value = float(g["current_value"])
            if "archived" in g:
                goal.archived = bool(g.get("archived"))
            session.flush()
            if old_id is not None:
                goal_map[int(old_id)] = goal.id
            counts["merged_goals"] += 1
        else:
            goal = Goal(
                title=title,
                description=g.get("description") or "",
                target_value=float(g.get("target_value") or 1),
                unit=g.get("unit") or "units",
                daily_quota=float(g.get("daily_quota") or 1),
                current_value=float(g.get("current_value") or 0),
                archived=bool(g.get("archived", False)),
            )
            session.add(goal)
            session.flush()
            if old_id is not None:
                goal_map[int(old_id)] = goal.id
            existing_goals[key] = goal
            counts["goals"] += 1

    for t in data.get("tasks") or []:
        old_id = t.get("id")
        title = (t.get("title") or "Задача").strip()
        key = title.lower()
        old_gid = t.get("goal_id")
        new_gid = goal_map.get(int(old_gid)) if old_gid is not None else None
        if mode == "merge" and key in existing_tasks:
            task = existing_tasks[key]
            task.description = t.get("description") if t.get("description") is not None else task.description
            if t.get("status"):
                task.status = t["status"]
            if t.get("priority"):
                task.priority = t["priority"]
            if "due_date" in t:
                task.due_date = _parse_date(t.get("due_date"))
            if new_gid is not None:
                task.goal_id = new_gid
            if "color_tag" in t:
                task.color_tag = t.get("color_tag")
            if "completed_at" in t:
                task.completed_at = _parse_dt(t.get("completed_at"))
            if "archived" in t:
                task.archived = bool(t.get("archived"))
            if "pinned" in t:
                task.pinned = bool(t.get("pinned"))
            if "recur_rule" in t and t.get("recur_rule"):
                task.recur_rule = str(t.get("recur_rule") or "none")
            if "recur_anchor" in t:
                task.recur_anchor = _parse_date(t.get("recur_anchor"))
            if "estimated_min" in t:
                raw_em = t.get("estimated_min")
                try:
                    task.estimated_min = int(raw_em) if raw_em is not None else None
                except (TypeError, ValueError):
                    pass
            if "inbox" in t:
                task.inbox = bool(t.get("inbox"))
            session.flush()
            if old_id is not None:
                task_map[int(old_id)] = task.id
            counts["merged_tasks"] += 1
        else:
            raw_em = t.get("estimated_min")
            try:
                em_val = int(raw_em) if raw_em is not None else None
            except (TypeError, ValueError):
                em_val = None
            task = Task(
                title=title,
                description=t.get("description") or "",
                status=t.get("status") or "todo",
                priority=t.get("priority") or "medium",
                due_date=_parse_date(t.get("due_date")),
                goal_id=new_gid,
                color_tag=t.get("color_tag"),
                pinned=bool(t.get("pinned", False)),
                archived=bool(t.get("archived", False)),
                recur_rule=str(t.get("recur_rule") or "none"),
                recur_anchor=_parse_date(t.get("recur_anchor")),
                estimated_min=em_val,
                inbox=bool(t.get("inbox", False)),
                completed_at=_parse_dt(t.get("completed_at")),
            )
            session.add(task)
            session.flush()
            if old_id is not None:
                task_map[int(old_id)] = task.id
            existing_tasks[key] = task
            counts["tasks"] += 1

    for s in data.get("subtasks") or []:
        old_tid = s.get("task_id")
        if old_tid is None:
            continue
        new_tid = task_map.get(int(old_tid))
        if new_tid is None:
            continue
        title = (s.get("title") or "").strip()
        if not title:
            continue
        # Skip duplicate title on same task when merging
        if mode == "merge":
            dup = session.scalar(
                select(Subtask).where(
                    Subtask.task_id == new_tid, Subtask.title == title
                )
            )
            if dup:
                continue
        sub = Subtask(
            task_id=new_tid,
            title=title,
            done=bool(s.get("done")),
            position=int(s.get("position") or 0),
        )
        session.add(sub)
        counts["subtasks"] += 1

    for lg in data.get("progress_logs") or []:
        old_gid = lg.get("goal_id")
        if old_gid is None:
            continue
        new_gid = goal_map.get(int(old_gid))
        if new_gid is None:
            continue
        amount = float(lg.get("amount") or 0)
        if amount <= 0:
            continue
        log = ProgressLog(
            goal_id=new_gid,
            amount=amount,
            note=lg.get("note") or "",
            logged_at=_parse_dt(lg.get("logged_at")) or datetime.now(),
        )
        session.add(log)
        counts["progress_logs"] += 1

    for n in data.get("roadmap_nodes") or []:
        old_id = n.get("id")
        old_tid = n.get("task_id")
        new_tid = task_map.get(int(old_tid)) if old_tid is not None else None
        node = RoadmapNode(
            title=(n.get("title") or "Узел").strip(),
            x=float(n.get("x") or 40),
            y=float(n.get("y") or 40),
            status=n.get("status") or "pending",
            task_id=new_tid,
        )
        session.add(node)
        session.flush()
        if old_id is not None:
            node_map[int(old_id)] = node.id
        counts["roadmap_nodes"] += 1

    for e in data.get("roadmap_edges") or []:
        frm = e.get("from_node_id")
        to = e.get("to_node_id")
        if frm is None or to is None:
            continue
        nf = node_map.get(int(frm))
        nt = node_map.get(int(to))
        if nf is None or nt is None:
            continue
        session.add(RoadmapEdge(from_node_id=nf, to_node_id=nt))
        counts["roadmap_edges"] += 1

    for ts in data.get("time_sessions") or []:
        old_tid = ts.get("task_id")
        new_tid = task_map.get(int(old_tid)) if old_tid is not None else None
        dur = int(ts.get("duration_sec") or 25 * 60)
        rem = ts.get("remaining_sec")
        session.add(
            TimeSession(
                task_id=new_tid,
                label=ts.get("label") or "Фокус",
                duration_sec=dur,
                remaining_sec=int(rem) if rem is not None else dur,
                status=ts.get("status") or "paused",
                note=ts.get("note") or "",
                started_at=_parse_dt(ts.get("started_at")),
            )
        )
        counts["time_sessions"] += 1

    # --- canvas nodes / edges (schema 13) ---
    canvas_map: dict[int, int] = {}
    if mode == "replace":
        # already cleared in _clear_all; no-op
        pass
    elif mode == "merge" and (data.get("canvas_nodes") or data.get("canvas_edges")):
        # Merge: keep existing section nodes; only add free notes / missing refs
        pass

    existing_canvas_refs: set[tuple[str, str]] = set()
    if mode == "merge":
        for cn in session.scalars(select(CanvasNode)).all():
            existing_canvas_refs.add(((cn.kind or ""), (cn.ref or "").strip().lower()))

    for n in data.get("canvas_nodes") or []:
        old_id = n.get("id")
        kind = (n.get("kind") or "note").strip() or "note"
        ref_raw = n.get("ref") or ""
        if kind in ("section", "note"):
            try:
                ref = notes_service.sanitize_filename(str(ref_raw)) if str(ref_raw).strip() else ""
            except ValueError:
                try:
                    base = str(ref_raw).replace("\\", "/").split("/")[-1]
                    ref = notes_service.sanitize_filename(base) if base else ""
                except ValueError:
                    continue
        else:
            ref = str(ref_raw)[:255]
        key = (kind, ref.strip().lower())
        if mode == "merge" and key in existing_canvas_refs and kind == "section":
            # Reuse existing section node for id remapping
            match = session.scalar(
                select(CanvasNode).where(
                    CanvasNode.kind == kind, CanvasNode.ref == ref
                )
            )
            if match is not None and old_id is not None:
                canvas_map[int(old_id)] = match.id
            continue
        node = CanvasNode(
            title=(n.get("title") or "Узел").strip()[:200],
            x=float(n.get("x") or 40),
            y=float(n.get("y") or 40),
            kind=kind,
            ref=ref,
            color=n.get("color"),
            w=float(n.get("w") or 160),
            h=float(n.get("h") or 72),
        )
        session.add(node)
        session.flush()
        if old_id is not None:
            canvas_map[int(old_id)] = node.id
        existing_canvas_refs.add(key)
        counts["canvas_nodes"] += 1

    for e in data.get("canvas_edges") or []:
        frm = e.get("from_node_id")
        to = e.get("to_node_id")
        if frm is None or to is None:
            continue
        nf = canvas_map.get(int(frm))
        nt = canvas_map.get(int(to))
        if nf is None or nt is None:
            continue
        if mode == "merge":
            dup = session.scalar(
                select(CanvasEdge).where(
                    CanvasEdge.from_node_id == nf, CanvasEdge.to_node_id == nt
                )
            )
            if dup:
                continue
        session.add(CanvasEdge(from_node_id=nf, to_node_id=nt))
        counts["canvas_edges"] += 1

    _import_notes_vault(data.get("notes"), counts=counts)

    _apply_settings(session, data.get("settings"))
    set_meta(session, "seeded", "1")
    session.flush()
    # Logs may have been appended without updating goal.current_value
    from app.services import goal_service

    goal_service.repair_all_goal_values(session)
    session.commit()
    return counts

def summarize_export(
    data: dict | None = None, path: Path | str | None = None
) -> dict:
    """Counts + byte size for an export payload or file. Settings always counted."""
    payload = data
    size = 0
    pth = Path(path) if path else None
    if pth is not None and pth.is_file():
        size = pth.stat().st_size
        if payload is None:
            payload = json.loads(pth.read_text(encoding="utf-8"))
    if payload is None:
        payload = {}
    if size <= 0:
        size = len(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
    settings = payload.get("settings")
    notes = payload.get("notes")
    n_notes = len(notes) if isinstance(notes, dict) else 0
    return {
        "tasks": len(payload.get("tasks") or []),
        "goals": len(payload.get("goals") or []),
        "subtasks": len(payload.get("subtasks") or []),
        "progress_logs": len(payload.get("progress_logs") or []),
        "notes": n_notes,
        "canvas_nodes": len(payload.get("canvas_nodes") or []),
        "canvas_edges": len(payload.get("canvas_edges") or []),
        "has_settings": isinstance(settings, dict) and bool(settings),
        "size_bytes": int(size),
    }


def format_size_bytes(n: int) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 0
    if n < 1024:
        return f"{n} Б"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} КБ"
    return f"{n / (1024 * 1024):.1f} МБ"


def format_export_snack(summary: dict, filename: str | None = None) -> str:
    """One-line RU snack: counts + size (settings mentioned when present)."""
    size_s = format_size_bytes(summary.get("size_bytes") or 0)
    n_tasks = int(summary.get("tasks") or 0)
    n_goals = int(summary.get("goals") or 0)
    extra = ", настройки" if summary.get("has_settings") else ""
    n_notes = int(summary.get("notes") or 0)
    if n_notes:
        extra += f", {n_notes} заметок"
    n_cn = int(summary.get("canvas_nodes") or 0)
    if n_cn:
        extra += f", холст {n_cn}"
    msg = f"Экспорт: {n_tasks} задач, {n_goals} целей{extra} · {size_s}"
    if filename:
        msg += f" · {filename}"
    return msg


def export_tasks_csv(session: Session, path: Path | None = None) -> Path:
    """Write UTF-8 CSV (with BOM) of all tasks. Default under data/export-tasks-*.csv."""
    from app.db import get_db_path

    if path is None:
        folder = get_db_path().parent
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = folder / f"export-tasks-{stamp}.csv"
    else:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

    cols = [
        "id",
        "title",
        "status",
        "priority",
        "due_date",
        "goal_id",
        "color_tag",
        "pinned",
        "archived",
        "inbox",
        "recur_rule",
        "estimated_min",
        "completed_at",
    ]
    rows = session.scalars(select(Task).order_by(Task.id)).all()
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for t in rows:
            writer.writerow(
                {
                    "id": t.id,
                    "title": t.title,
                    "status": t.status,
                    "priority": t.priority,
                    "due_date": _ser(t.due_date) or "",
                    "goal_id": t.goal_id if t.goal_id is not None else "",
                    "color_tag": t.color_tag or "",
                    "pinned": int(bool(getattr(t, "pinned", False))),
                    "archived": int(bool(getattr(t, "archived", False))),
                    "inbox": int(bool(getattr(t, "inbox", False))),
                    "recur_rule": getattr(t, "recur_rule", None) or "none",
                    "estimated_min": getattr(t, "estimated_min", None)
                    if getattr(t, "estimated_min", None) is not None
                    else "",
                    "completed_at": _ser(t.completed_at) or "",
                }
            )
    return path
