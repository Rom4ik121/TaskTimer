"""Database engine / session helpers + lightweight schema migration."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    AppMeta,
    Base,
    CanvasNode,
    Goal,
    ProgressLog,
    RoadmapNode,
    Subtask,
    Task,
    TimeSession,
)

SCHEMA_VERSION = "13"

_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "tasktimer.db"
_ENGINE = None
_SessionLocal = None

DEFAULT_SETTINGS = {
    "display_name": "Рома",
    "accent_hex": "#FF8A00",
    "week_starts_monday": "1",
    "pomodoro_work_min": "25",
    "pomodoro_break_min": "5",
    "archive_on_recur_done": "0",
    "quiet_start": "22",
    "quiet_end": "8",
    "auto_complete_subtasks": "0",
    "compact_ui": "0",
    "haptics_enabled": "1",
    "wind_down_hour": "18",
    "weekly_task_target": "10",
}


def get_db_path() -> Path:
    return _DB_PATH


def _migrate_schema(engine) -> None:
    """Add missing columns / ensure app_meta without Alembic."""
    with engine.begin() as conn:
        Base.metadata.create_all(conn)

        def cols(table: str) -> set[str]:
            rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            return {r[1] for r in rows}

        task_cols = cols("tasks")
        if "completed_at" not in task_cols:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN completed_at DATETIME"))
        if "color_tag" not in task_cols:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN color_tag VARCHAR(32)"))
        if "archived" not in task_cols:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN archived BOOLEAN DEFAULT 0"))
        conn.execute(text("UPDATE tasks SET archived = 0 WHERE archived IS NULL"))
        if "recur_rule" not in task_cols:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN recur_rule VARCHAR(16) DEFAULT 'none'"))
        conn.execute(text("UPDATE tasks SET recur_rule = 'none' WHERE recur_rule IS NULL"))
        if "recur_anchor" not in task_cols:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN recur_anchor DATE"))
        if "pinned" not in task_cols:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN pinned BOOLEAN DEFAULT 0"))
        conn.execute(text("UPDATE tasks SET pinned = 0 WHERE pinned IS NULL"))
        if "estimated_min" not in task_cols:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN estimated_min INTEGER"))
        if "inbox" not in task_cols:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN inbox BOOLEAN DEFAULT 0"))
        conn.execute(text("UPDATE tasks SET inbox = 0 WHERE inbox IS NULL"))

        goal_cols = cols("goals")
        if "archived" not in goal_cols:
            conn.execute(text("ALTER TABLE goals ADD COLUMN archived BOOLEAN DEFAULT 0"))
        conn.execute(text("UPDATE goals SET archived = 0 WHERE archived IS NULL"))

        sess_cols = cols("time_sessions")
        if "note" not in sess_cols:
            conn.execute(text("ALTER TABLE time_sessions ADD COLUMN note TEXT DEFAULT ''"))
        conn.execute(text("UPDATE time_sessions SET note = '' WHERE note IS NULL"))

        # Performance indexes (idempotent)
        for idx_sql in (
            "CREATE INDEX IF NOT EXISTS ix_tasks_status ON tasks (status)",
            "CREATE INDEX IF NOT EXISTS ix_tasks_due_date ON tasks (due_date)",
            "CREATE INDEX IF NOT EXISTS ix_tasks_goal_id ON tasks (goal_id)",
            "CREATE INDEX IF NOT EXISTS ix_tasks_archived ON tasks (archived)",
            "CREATE INDEX IF NOT EXISTS ix_tasks_pinned ON tasks (pinned)",
            "CREATE INDEX IF NOT EXISTS ix_tasks_priority ON tasks (priority)",
            "CREATE INDEX IF NOT EXISTS ix_tasks_recur_rule ON tasks (recur_rule)",
            "CREATE INDEX IF NOT EXISTS ix_tasks_inbox ON tasks (inbox)",
            "CREATE INDEX IF NOT EXISTS ix_goals_archived ON goals (archived)",
            "CREATE INDEX IF NOT EXISTS ix_progress_logs_logged_at ON progress_logs (logged_at)",
            "CREATE INDEX IF NOT EXISTS ix_progress_logs_goal_id ON progress_logs (goal_id)",
            "CREATE INDEX IF NOT EXISTS ix_time_sessions_status ON time_sessions (status)",
            "CREATE INDEX IF NOT EXISTS ix_time_sessions_created_at ON time_sessions (created_at)",
            "CREATE INDEX IF NOT EXISTS ix_canvas_nodes_kind ON canvas_nodes (kind)",
            "CREATE INDEX IF NOT EXISTS ix_canvas_edges_from ON canvas_edges (from_node_id)",
            "CREATE INDEX IF NOT EXISTS ix_canvas_edges_to ON canvas_edges (to_node_id)",
        ):
            conn.execute(text(idx_sql))

        # Ensure schema_version meta row
        existing = conn.execute(
            text("SELECT value FROM app_meta WHERE key = 'schema_version'")
        ).fetchone()
        if existing is None:
            conn.execute(
                text(
                    "INSERT INTO app_meta (key, value) VALUES ('schema_version', :v)"
                ),
                {"v": SCHEMA_VERSION},
            )
        else:
            conn.execute(
                text("UPDATE app_meta SET value = :v WHERE key = 'schema_version'"),
                {"v": SCHEMA_VERSION},
            )

        # Default settings keys
        for key, value in DEFAULT_SETTINGS.items():
            row = conn.execute(
                text("SELECT value FROM app_meta WHERE key = :k"), {"k": key}
            ).fetchone()
            if row is None:
                conn.execute(
                    text("INSERT INTO app_meta (key, value) VALUES (:k, :v)"),
                    {"k": key, "v": value},
                )

        # Legacy installs (already seeded) skip first-run onboarding
        seeded_row = conn.execute(
            text("SELECT value FROM app_meta WHERE key = 'seeded'")
        ).fetchone()
        onboarded_row = conn.execute(
            text("SELECT value FROM app_meta WHERE key = 'onboarded'")
        ).fetchone()
        if (
            seeded_row is not None
            and seeded_row[0] == "1"
            and onboarded_row is None
        ):
            conn.execute(
                text("INSERT INTO app_meta (key, value) VALUES ('onboarded', '1')")
            )

        # Backfill completed_at for legacy done tasks (once)
        conn.execute(
            text(
                "UPDATE tasks SET completed_at = COALESCE(updated_at, CURRENT_TIMESTAMP) "
                "WHERE status = 'done' AND completed_at IS NULL"
            )
        )


def init_db() -> None:
    global _ENGINE, _SessionLocal
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ENGINE = create_engine(
        f"sqlite:///{_DB_PATH}",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    from sqlalchemy import event

    @event.listens_for(_ENGINE, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    _migrate_schema(_ENGINE)
    _SessionLocal = sessionmaker(
        bind=_ENGINE, autoflush=False, autocommit=False, expire_on_commit=False
    )
    # Heal any goal.current_value drift vs progress_logs
    try:
        from app.services import goal_service

        with _SessionLocal() as session:
            goal_service.repair_all_goal_values(session)
    except Exception as exc:
        import sys

        print(f"[TaskTimer] goal repair warning: {exc}", file=sys.stderr)
    # Vault + infinite canvas section nodes (schema 13+)
    try:
        from app.services import canvas_service
        from app.services import notes_service

        notes_service.ensure_vault()
        with _SessionLocal() as session:
            canvas_service.ensure_canvas_seeded(session)
    except Exception as exc:
        # Non-fatal for core CRUD, but must not fail silently forever
        import sys

        print(f"[TaskTimer] vault/canvas seed warning: {exc}", file=sys.stderr)


def get_session() -> Session:
    if _SessionLocal is None:
        init_db()
    assert _SessionLocal is not None
    return _SessionLocal()


def get_meta(session: Session, key: str) -> str | None:
    row = session.get(AppMeta, key)
    return row.value if row else None


def set_meta(session: Session, key: str, value: str) -> None:
    row = session.get(AppMeta, key)
    if row:
        row.value = value
    else:
        session.add(AppMeta(key=key, value=value))


def is_empty() -> bool:
    """True only when DB was never seeded and all main tables are empty.

    Once the ``seeded`` flag is set, never returns True — even if the user
    deletes every task/goal. Prevents re-seeding after wipe.
    """
    with get_session() as session:
        if get_meta(session, "seeded") == "1":
            return False
        counts = [
            session.scalar(select(func.count()).select_from(Task)) or 0,
            session.scalar(select(func.count()).select_from(Goal)) or 0,
            session.scalar(select(func.count()).select_from(ProgressLog)) or 0,
            session.scalar(select(func.count()).select_from(RoadmapNode)) or 0,
            session.scalar(select(func.count()).select_from(TimeSession)) or 0,
            session.scalar(select(func.count()).select_from(Subtask)) or 0,
        ]
        if any(c > 0 for c in counts):
            # Residual data without flag — mark seeded so we don't wipe/reseed
            set_meta(session, "seeded", "1")
            session.commit()
            return False
        return True
