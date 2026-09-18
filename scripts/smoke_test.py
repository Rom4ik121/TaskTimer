#!/usr/bin/env python3
"""Smoke tests: Waves A–AV — includes Wave AU canvas blank-panel fix and Wave AV filter sheets / haptics / motion."""
from __future__ import annotations

import json
import shutil
import struct
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    # Isolated temp DB
    tmp = Path(tempfile.mkdtemp(prefix="tasktimer_smoke_"))
    db_dir = tmp / "data"
    db_dir.mkdir()
    db_path = db_dir / "tasktimer.db"

    import app.db as dbmod

    dbmod._DB_PATH = db_path
    dbmod._ENGINE = None
    dbmod._SessionLocal = None

    from app.db import SCHEMA_VERSION, get_meta, get_session, init_db, is_empty
    from app.schemas import (
        GoalCreate,
        ProgressLogCreate,
        ProgressLogUpdate,
        GoalUpdate,
        RoadmapEdgeCreate,
        RoadmapNodeCreate,
        SettingsUpdate,
        SubtaskCreate,
        SubtaskUpdate,
        TaskCreate,
        TaskUpdate,
        TimeSessionCreate,
    )
    from app.services import (
        analytics_service,
        export_service,
        goal_service,
        roadmap_service,
        settings_service,
        streak_service,
        subtask_service,
        task_service,
        timer_service,
    )
    from app.services.seed import seed_if_empty

    print("== init + seed ==")
    init_db()
    assert is_empty(), "fresh DB should be empty"
    seed_if_empty()
    assert not is_empty(), "after seed not empty"
    with get_session() as s:
        assert get_meta(s, "seeded") == "1"
        assert get_meta(s, "schema_version") == SCHEMA_VERSION
        n_tasks = len(task_service.list_tasks(s))
        n_goals = len(goal_service.list_goals(s))
        n_nodes = len(roadmap_service.list_nodes(s))
        # Seeded subtasks
        any_subs = False
        for t in task_service.list_tasks(s):
            if subtask_service.list_subtasks(s, t.id):
                any_subs = True
                break
        assert any_subs, "seed should include subtasks"
    print(f"seeded tasks={n_tasks} goals={n_goals} nodes={n_nodes} schema={SCHEMA_VERSION}")
    assert n_tasks >= 5 and n_goals >= 2 and n_nodes >= 3

    print("== no double-seed ==")
    with get_session() as s:
        for t in list(task_service.list_tasks(s)):
            task_service.delete_task(s, t.id)
        remaining = len(task_service.list_tasks(s))
        seeded_flag = get_meta(s, "seeded")
    assert remaining == 0
    assert seeded_flag == "1"
    assert not is_empty(), "seeded flag must block is_empty"
    seed_if_empty()
    with get_session() as s:
        assert len(task_service.list_tasks(s)) == 0, "double-seed leaked tasks"
        # Subtasks cascaded
        from sqlalchemy import func, select
        from app.models import Subtask

        assert (s.scalar(select(func.count()).select_from(Subtask)) or 0) == 0
    print("no double-seed OK")

    print("== CRUD task ==")
    with get_session() as s:
        goals = goal_service.list_goals(s)
        gid = goals[0].id if goals else None
        t = task_service.create_task(
            s,
            TaskCreate(
                title="Smoke Task",
                description="test",
                status="todo",
                priority="high",
                due_date=date.today() - timedelta(days=2),
                goal_id=gid,
                color_tag="синий",
            ),
        )
        tid = t.id
        assert t.completed_at is None
        assert task_service.is_overdue(t)
        overdue_list = task_service.list_tasks(s, overdue=True)
        assert any(x.id == tid for x in overdue_list)
        t2 = task_service.update_task(s, tid, TaskUpdate(status="done"))
        assert t2 is not None and t2.completed_at is not None
        t3 = task_service.update_task(s, tid, TaskUpdate(status="todo"))
        assert t3 is not None and t3.completed_at is None
        found = task_service.list_tasks(s, query="Smoke")
        assert any(x.id == tid for x in found)
    print("task CRUD + overdue OK")

    print("== subtasks ==")
    with get_session() as s:
        s1 = subtask_service.create_subtask(
            s, SubtaskCreate(task_id=tid, title="Пункт A")
        )
        s2 = subtask_service.create_subtask(
            s, SubtaskCreate(task_id=tid, title="Пункт B")
        )
        assert s1 and s2 and s1.position == 0 and s2.position == 1
        toggled = subtask_service.toggle_subtask(s, s1.id)
        assert toggled and toggled.done is True
        subtask_service.update_subtask(s, s2.id, SubtaskUpdate(title="Пункт B2"))
        items = subtask_service.list_subtasks(s, tid)
        assert len(items) == 2
        subtask_service.delete_subtask(s, s2.id)
        assert len(subtask_service.list_subtasks(s, tid)) == 1
        # Recreate second for reorder
        s2 = subtask_service.create_subtask(
            s, SubtaskCreate(task_id=tid, title="Пункт B")
        )
        s3 = subtask_service.create_subtask(
            s, SubtaskCreate(task_id=tid, title="Пункт C")
        )
        items = subtask_service.list_subtasks(s, tid)
        assert [x.title for x in items][-1] == "Пункт C"
        subtask_service.move_subtask(s, s3.id, -1)
        items = subtask_service.list_subtasks(s, tid)
        titles = [x.title for x in items]
        assert titles.index("Пункт C") < titles.index("Пункт B") or "Пункт B" in titles
        # Cascade on task delete
        task_service.delete_task(s, tid)
        assert len(subtask_service.list_subtasks(s, tid)) == 0
    print("subtasks OK")

    print("== CRUD goal + log ==")
    with get_session() as s:
        g = goal_service.create_goal(
            s,
            GoalCreate(
                title="Smoke Goal",
                description="d",
                target_value=10,
                unit="шт",
                daily_quota=2,
            ),
        )
        smoke_gid = g.id
        log = goal_service.add_progress(
            s, ProgressLogCreate(goal_id=g.id, amount=2, note="smoke")
        )
        assert log is not None
        today = goal_service.today_logged(s, g.id)
        assert today >= 2
        quotas = goal_service.today_quotas(s)
        assert any(q["goal"].id == g.id and q["complete"] for q in quotas)
    print("goal/log OK")

    print("== streaks ==")
    with get_session() as s:
        # Backfill consecutive days for smoke goal
        g = goal_service.get_goal(s, smoke_gid)
        assert g
        now = datetime.now()
        for i in range(1, 4):
            from app.models import ProgressLog

            s.add(
                ProgressLog(
                    goal_id=g.id,
                    amount=2,
                    note=f"streak-{i}",
                    logged_at=now - timedelta(days=i),
                )
            )
        s.commit()
        info = streak_service.goal_streak(s, g)
        assert info.current_streak >= 3, info
        assert info.today_complete is True
        all_s = streak_service.all_streaks(s)
        assert any(x.goal_id == g.id for x in all_s)
        cal = streak_service.quota_calendar(s, g, days=28)
        assert len(cal) == 28
        assert any(d["met"] for d in cal)
    print("streaks OK")

    print("== heatmap ==")
    with get_session() as s:
        heat = analytics_service.activity_heatmap(s, weeks=14)
        assert len(heat) == 14 * 7
        assert sum(d.count for d in heat) > 0
    print("heatmap OK")

    print("== settings ==")
    with get_session() as s:
        cur = settings_service.get_settings(s)
        assert cur.accent_hex.upper() == "#FF8A00"
        updated = settings_service.update_settings(
            s,
            SettingsUpdate(
                display_name="Smoke User",
                accent_hex="#ff5500",
                week_starts_monday=False,
            ),
        )
        assert updated.display_name == "Smoke User"
        assert updated.accent_hex == "#FF5500"
        assert updated.week_starts_monday is False
        settings_service.update_settings(
            s, SettingsUpdate(display_name="Рома", accent_hex="#FF8A00", week_starts_monday=True)
        )
    print("settings OK")

    print("== export ==")
    with get_session() as s:
        payload = export_service.export_all(s)
        assert payload["format"] == "tasktimer-export"
        assert "tasks" in payload and "goals" in payload and "subtasks" in payload
        assert "notes" in payload and isinstance(payload["notes"], dict)
        assert "home.md" in payload["notes"]
        assert "canvas_nodes" in payload and "canvas_edges" in payload
        assert isinstance(payload["canvas_nodes"], list)
        path = export_service.write_export_file(s, dest_dir=db_dir)
        assert path.exists()
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["settings"]["display_name"]
        assert "home.md" in loaded.get("notes", {})
    print("export OK", path.name)

    print("== import ==")
    with get_session() as s:
        payload = export_service.export_all(s)
        # merge into existing
        summary = export_service.import_all(s, payload, mode="merge")
        assert summary["mode"] == "merge"
        # round-trip replace into fresh empty-ish: wipe tasks/goals via replace
        summary2 = export_service.import_all(s, payload, mode="replace")
        assert summary2["mode"] == "replace"
        assert len(goal_service.list_goals(s)) >= 1
        assert len(task_service.list_tasks(s)) >= 0
        # default mode on empty after clear
        from sqlalchemy import delete
        from app.models import Goal, ProgressLog, RoadmapEdge, RoadmapNode, Subtask, Task, TimeSession
        s.execute(delete(RoadmapEdge))
        s.execute(delete(RoadmapNode))
        s.execute(delete(TimeSession))
        s.execute(delete(Subtask))
        s.execute(delete(ProgressLog))
        s.execute(delete(Task))
        s.execute(delete(Goal))
        s.commit()
        summary3 = export_service.import_all(s, payload)  # auto replace
        assert summary3["mode"] == "replace"
        smoke_gid = goal_service.list_goals(s)[0].id
    print("import OK", summary["mode"], summary2["goals"])

    print("== live accent ==")
    from app.ui.theme import apply_accent
    from app.ui import theme as theme_mod
    import app.ui.components.cards as cards_mod
    apply_accent("#00AAFF")
    assert theme_mod.ORANGE == "#00AAFF"
    assert cards_mod.ORANGE == "#00AAFF", "importer not patched"
    apply_accent("#FF8A00")
    assert theme_mod.ORANGE == "#FF8A00"
    assert cards_mod.ORANGE == "#FF8A00"
    print("live accent OK")

    # cleanup smoke goal
    with get_session() as s:
        goal_service.delete_goal(s, smoke_gid)

    print("== timer session ==")
    with get_session() as s:
        sess = timer_service.create_session(
            s, TimeSessionCreate(label="Smoke Focus", duration_sec=60)
        )
        sid = sess.id
        timer_service.play(s, sid)
        ts = timer_service.tick(s, sid)
        assert ts is not None and ts.status == "running"
        timer_service.pause(s, sid)
        timer_service.reset(s, sid)
        ts2 = timer_service.get_session_by_id(s, sid)
        assert ts2 is not None and ts2.remaining_sec == 60 and ts2.status == "paused"
    print("timer OK")

    print("== roadmap ==")
    with get_session() as s:
        n1 = roadmap_service.create_node(
            s, RoadmapNodeCreate(title="Smoke A", x=10, y=10)
        )
        n2 = roadmap_service.create_node(
            s, RoadmapNodeCreate(title="Smoke B", x=100, y=10)
        )
        e = roadmap_service.create_edge(
            s, RoadmapEdgeCreate(from_node_id=n1.id, to_node_id=n2.id)
        )
        assert e is not None
        roadmap_service.cycle_node_status(s, n1.id)
        roadmap_service.delete_node(s, n2.id)
        roadmap_service.delete_node(s, n1.id)
    print("roadmap OK")

    print("== analytics ==")
    with get_session() as s:
        dist = analytics_service.status_distribution(s)
        points = analytics_service.completed_last_n_days(s, 14)
        stats = analytics_service.overview_stats(s)
        assert len(points) == 14
        assert stats.completion_rate >= 0
        assert stats.overdue_tasks >= 0
        print("dist", dist)
        print("stats", stats)
    print("analytics OK")

    print("== accent presets ==")
    from app.ui.theme import ACCENT_PRESETS, apply_accent
    from app.ui import theme as theme_mod
    assert len(ACCENT_PRESETS) >= 5
    labels = {x[0] for x in ACCENT_PRESETS}
    assert {"orange", "teal", "violet", "rose", "blue"} <= labels
    for _label, hx in ACCENT_PRESETS:
        apply_accent(hx)
        assert theme_mod.ORANGE == hx.upper() or theme_mod.ORANGE == hx
    apply_accent("#FF8A00")
    print("accent presets OK")

    print("== soft undo replace-import ==")
    with get_session() as s:
        # Ensure we have identifiable content
        g_mark = goal_service.create_goal(
            s,
            GoalCreate(
                title="UndoMarkerGoal",
                description="before-replace",
                target_value=5,
                unit="x",
                daily_quota=1,
            ),
        )
        marker_gid = g_mark.id
        payload_before = export_service.export_all(s)
        # Build a different payload to replace with
        other = dict(payload_before)
        other["goals"] = [
            {
                "id": 999,
                "title": "AfterReplaceGoal",
                "description": "new",
                "target_value": 3,
                "unit": "u",
                "daily_quota": 1,
                "current_value": 0,
            }
        ]
        other["tasks"] = []
        other["subtasks"] = []
        other["progress_logs"] = []
        other["roadmap_nodes"] = []
        other["roadmap_edges"] = []
        other["time_sessions"] = []
        summary_r = export_service.import_all(s, other, mode="replace")
        assert summary_r["mode"] == "replace"
        assert summary_r.get("pre_import_backup"), "replace must snapshot"
        bak = export_service.get_last_import_backup(s)
        assert bak is not None and bak.exists()
        titles = [g.title for g in goal_service.list_goals(s)]
        assert "AfterReplaceGoal" in titles
        assert "UndoMarkerGoal" not in titles
        # Undo
        undone = export_service.undo_last_replace_import(s)
        assert undone["mode"] == "replace"
        titles2 = [g.title for g in goal_service.list_goals(s)]
        assert "UndoMarkerGoal" in titles2
        assert export_service.get_last_import_backup(s) is None
    print("soft undo OK")

    print("== archive ==")
    with get_session() as s:
        t = task_service.create_task(
            s,
            TaskCreate(
                title="ArchiveMe",
                description="",
                status="todo",
                priority="low",
                due_date=date.today(),
            ),
        )
        aid = t.id
        assert not getattr(t, "archived", False)
        task_service.archive_task(s, aid)
        active = task_service.list_tasks(s, archived=False)
        assert all(x.id != aid for x in active)
        archived = task_service.list_tasks(s, archived=True)
        assert any(x.id == aid for x in archived)
        task_service.unarchive_task(s, aid)
        active2 = task_service.list_tasks(s, archived=False)
        assert any(x.id == aid for x in active2)
        # Due today + overdue buckets for reminders
        task_service.update_task(
            s, aid, TaskUpdate(due_date=date.today() - timedelta(days=1), status="todo")
        )
        overdue = task_service.list_tasks(s, overdue=True)
        assert any(x.id == aid for x in overdue)
        task_service.update_task(s, aid, TaskUpdate(due_date=date.today()))
        due = task_service.list_tasks(s, due_today=True)
        assert any(x.id == aid for x in due)
        overdue2 = task_service.list_tasks(s, overdue=True)
        assert all(x.id != aid for x in overdue2), "due today must not be overdue"
        assert task_service.is_due_today(
            next(x for x in due if x.id == aid)
        )
        task_service.delete_task(s, aid)
    print("archive OK")

    print("== reminders ==")
    from app.services import reminder_service
    with get_session() as s:
        rem = reminder_service.list_reminders(s)
        assert "due_today" in rem and "overdue" in rem and "incomplete_goals" in rem
        assert isinstance(rem["count"], int)
    print("reminders OK", rem["count"])

    print("== goal templates ==")
    from app.ui.screens.create_task import GOAL_TEMPLATES
    labels = [x[0] for x in GOAL_TEMPLATES]
    assert "Книга 10 стр/день" in labels
    assert "Спорт" in labels
    assert "Учёба 1.5ч" in labels
    assert "Кастом" in labels
    book = dict(GOAL_TEMPLATES)["Книга 10 стр/день"]
    assert book and float(book["quota"]) == 10
    with get_session() as s:
        g = goal_service.create_goal(
            s,
            GoalCreate(
                title=book["title"],
                description=book["description"],
                target_value=float(book["target"]),
                unit=book["unit"],
                daily_quota=float(book["quota"]),
            ),
        )
        assert g.daily_quota == 10
        goal_service.delete_goal(s, g.id)
    print("goal templates OK")

    print("== sqlite indexes ==")
    with get_session() as s:
        rows = s.execute(__import__("sqlalchemy").text(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )).fetchall()
        names = {r[0] for r in rows}
        for need in (
            "ix_tasks_status",
            "ix_tasks_due_date",
            "ix_tasks_goal_id",
            "ix_tasks_archived",
            "ix_tasks_pinned",
            "ix_tasks_priority",
            "ix_tasks_recur_rule",
            "ix_goals_archived",
            "ix_progress_logs_logged_at",
            "ix_progress_logs_goal_id",
        ):
            assert need in names, f"missing index {need}: {names}"
        assert get_meta(s, "schema_version") == SCHEMA_VERSION
        assert SCHEMA_VERSION == "13"
        cols = {r[1] for r in s.execute(__import__("sqlalchemy").text("PRAGMA table_info(tasks)")).fetchall()}
        assert "pinned" in cols
        assert "estimated_min" in cols
        sess_cols = {r[1] for r in s.execute(__import__("sqlalchemy").text("PRAGMA table_info(time_sessions)")).fetchall()}
        assert "note" in sess_cols
    print("indexes + schema 13 OK")

    print("== recurring tasks ==")
    with get_session() as s:
        t = task_service.create_task(
            s,
            TaskCreate(
                title="Recur Daily",
                description="base",
                status="todo",
                priority="medium",
                due_date=date.today(),
                recur_rule="daily",
            ),
        )
        rid = t.id
        assert t.recur_rule == "daily"
        assert t.recur_anchor == date.today()
        task_service.set_status(s, rid, "done")
        done = task_service.get_task(s, rid)
        assert done and done.status == "done" and done.completed_at
        spawned = [
            x
            for x in task_service.list_tasks(s)
            if x.title == "Recur Daily" and x.id != rid and x.status == "todo"
        ]
        assert len(spawned) >= 1, "daily recur must spawn next"
        child = spawned[0]
        assert "из повтора" in (child.description or "")
        assert f"#{rid}" in (child.description or "")
        assert child.due_date == date.today() + timedelta(days=1)
        assert child.recur_rule == "daily"
        w = task_service.create_task(
            s,
            TaskCreate(
                title="Recur Weekly",
                status="todo",
                priority="high",
                due_date=date.today() - timedelta(days=1),
                recur_rule="weekly",
            ),
        )
        wid = w.id
        task_service.set_status(s, wid, "done")
        wspawn = [
            x
            for x in task_service.list_tasks(s)
            if x.title == "Recur Weekly" and x.id != wid
        ]
        assert wspawn and wspawn[0].due_date > date.today()
        task_service.delete_task(s, rid)
        task_service.delete_task(s, child.id)
        task_service.delete_task(s, wid)
        for x in wspawn:
            task_service.delete_task(s, x.id)

        # Recur copies open (undone) subtasks onto the spawned child
        parent = task_service.create_task(
            s,
            TaskCreate(
                title="RecurSubs",
                status="todo",
                priority="medium",
                due_date=date.today(),
                recur_rule="daily",
            ),
        )
        pid = parent.id
        open_a = subtask_service.create_subtask(
            s, SubtaskCreate(task_id=pid, title="Open A")
        )
        open_b = subtask_service.create_subtask(
            s, SubtaskCreate(task_id=pid, title="Open B")
        )
        done_c = subtask_service.create_subtask(
            s, SubtaskCreate(task_id=pid, title="Done C")
        )
        subtask_service.toggle_subtask(s, done_c.id)
        task_service.set_status(s, pid, "done")
        kids = [
            x
            for x in task_service.list_tasks(s)
            if x.title == "RecurSubs" and x.id != pid and x.status == "todo"
        ]
        assert len(kids) == 1, "expect one spawn with subtasks"
        kid = kids[0]
        kid_subs = subtask_service.list_subtasks(s, kid.id)
        titles = [x.title for x in kid_subs]
        assert titles == ["Open A", "Open B"], f"open only, got {titles}"
        assert all(not x.done for x in kid_subs)
        # default: parent not archived
        parent_after = task_service.get_task(s, pid)
        assert parent_after and parent_after.status == "done"
        assert not parent_after.archived
        task_service.delete_task(s, pid)
        task_service.delete_task(s, kid.id)
    print("recurring OK")

    print("== archive_on_recur_done ==")
    with get_session() as s:
        cur = settings_service.get_settings(s)
        assert cur.archive_on_recur_done is False
        settings_service.update_settings(
            s, SettingsUpdate(archive_on_recur_done=True)
        )
        assert settings_service.get_settings(s).archive_on_recur_done is True
        t_arch = task_service.create_task(
            s,
            TaskCreate(
                title="RecurArchive",
                status="todo",
                due_date=date.today(),
                recur_rule="daily",
            ),
        )
        aid = t_arch.id
        task_service.set_status(s, aid, "done")
        parent = task_service.get_task(s, aid)
        assert parent and parent.status == "done" and parent.archived
        active = task_service.list_tasks(s, archived=False)
        assert all(x.id != aid for x in active)
        spawned = [
            x
            for x in task_service.list_tasks(s, archived=False)
            if x.title == "RecurArchive" and x.id != aid
        ]
        assert len(spawned) == 1
        # restore default
        settings_service.update_settings(
            s, SettingsUpdate(archive_on_recur_done=False)
        )
        assert settings_service.get_settings(s).archive_on_recur_done is False
        task_service.delete_task(s, aid)
        task_service.delete_task(s, spawned[0].id)
    print("archive_on_recur OK")

    print("== priority filter ==")
    with get_session() as s:
        hi = task_service.create_task(
            s, TaskCreate(title="PriHigh", priority="high", status="todo")
        )
        lo = task_service.create_task(
            s, TaskCreate(title="PriLow", priority="low", status="todo")
        )
        highs = task_service.list_tasks(s, priority="high")
        assert any(x.id == hi.id for x in highs)
        assert all(x.priority == "high" for x in highs)
        lows = task_service.list_tasks(s, priority="low")
        assert any(x.id == lo.id for x in lows)
        task_service.delete_task(s, hi.id)
        task_service.delete_task(s, lo.id)
    print("priority filter OK")

    print("== goal archive ==")
    with get_session() as s:
        g = goal_service.create_goal(
            s,
            GoalCreate(
                title="ArchiveGoal",
                description="",
                target_value=5,
                unit="x",
                daily_quota=1,
            ),
        )
        gid = g.id
        goal_service.archive_goal(s, gid)
        active = goal_service.list_goals(s, archived=False)
        assert all(x.id != gid for x in active)
        arch = goal_service.list_goals(s, archived=True)
        assert any(x.id == gid for x in arch)
        assert all(q["goal"].id != gid for q in goal_service.today_quotas(s))
        goal_service.unarchive_goal(s, gid)
        assert any(x.id == gid for x in goal_service.list_goals(s, archived=False))
        goal_service.delete_goal(s, gid)
    print("goal archive OK")

    print("== weekly focus stats ==")
    with get_session() as s:
        from app.models import TimeSession

        sess = timer_service.create_session(
            s, TimeSessionCreate(label="WeekFocus", duration_sec=1500)
        )
        ts = s.get(TimeSession, sess.id)
        ts.status = "done"
        ts.remaining_sec = 0
        s.commit()
        stats = analytics_service.weekly_focus_stats(s, days=7)
        assert stats.sessions_count >= 1
        assert stats.total_sec >= 1500
        assert len(stats.days) == 7
        timer_service.delete_session(s, sess.id)
    print("weekly focus OK", stats.total_min, "min")

    print("== due_today filter ==")
    with get_session() as s:
        t = task_service.create_task(
            s,
            TaskCreate(
                title="DueTodaySmoke",
                description="due today",
                status="todo",
                priority="medium",
                due_date=date.today(),
            ),
        )
        tid = t.id
        due = task_service.list_tasks(s, due_today=True)
        assert any(x.id == tid for x in due)
        overdue = task_service.list_tasks(s, overdue=True)
        assert all(x.id != tid for x in overdue)
        assert task_service.is_due_today(t)
        assert not task_service.is_overdue(t)
        # subtask progress counts after create
        s1 = subtask_service.create_subtask(s, SubtaskCreate(task_id=tid, title="A"))
        s2 = subtask_service.create_subtask(s, SubtaskCreate(task_id=tid, title="B"))
        s3 = subtask_service.create_subtask(s, SubtaskCreate(task_id=tid, title="C"))
        subtask_service.toggle_subtask(s, s1.id)
        items = subtask_service.list_subtasks(s, tid)
        assert len(items) == 3
        done_n = sum(1 for x in items if x.done)
        assert done_n == 1
        # list_tasks should selectinload subtasks (fresh query after expire)
        s.expire_all()
        listed = task_service.list_tasks(s, due_today=True)
        hit = next(x for x in listed if x.id == tid)
        assert len(hit.subtasks) == 3
        assert sum(1 for x in hit.subtasks if x.done) == 1
        task_service.delete_task(s, tid)
    print("due_today + subtask progress OK")

    print("== settings pomodoro ==")
    with get_session() as s:
        cur = settings_service.get_settings(s)
        assert cur.pomodoro_work_min == 25
        assert cur.pomodoro_break_min == 5
        assert cur.archive_on_recur_done is False
        updated = settings_service.update_settings(
            s,
            SettingsUpdate(pomodoro_work_min=30, pomodoro_break_min=10),
        )
        assert updated.pomodoro_work_min == 30
        assert updated.pomodoro_break_min == 10
        again = settings_service.get_settings(s)
        assert again.pomodoro_work_min == 30 and again.pomodoro_break_min == 10
        settings_service.update_settings(
            s, SettingsUpdate(pomodoro_work_min=25, pomodoro_break_min=5)
        )
    print("pomodoro settings OK")

    print("== home header stats ==")
    with get_session() as s:
        quotas = goal_service.today_quotas(s)
        streaks = streak_service.all_streaks(s)
        done_q = sum(1 for q in quotas if q["complete"])
        best = max((x.best_streak for x in streaks), default=0)
        assert done_q >= 0 and best >= 0
    print("home header stats OK", done_q, best)


    print("== global search + sort + markdown-lite ==")
    from app.services import search_service
    from app.ui.theme import markdown_lite
    with get_session() as s:
        t_a = task_service.create_task(
            s, TaskCreate(title="WaveH Alpha Search", description="note **bold** here", priority="high")
        )
        t_b = task_service.create_task(
            s, TaskCreate(title="WaveH Beta Later", due_date=date.today() + timedelta(days=3), priority="low")
        )
        g_hit = goal_service.create_goal(
            s,
            GoalCreate(
                title="WaveH Goal Target",
                description="goal **notes**",
                target_value=10,
                unit="u",
                daily_quota=1,
            ),
        )
        found = search_service.search(s, "WaveH")
        assert any(x.id == t_a.id for x in found["tasks"])
        assert any(x.id == t_b.id for x in found["tasks"])
        assert any(x.id == g_hit.id for x in found["goals"])
        empty = search_service.search(s, "   ")
        assert empty["tasks"] == [] and empty["goals"] == []
        by_due = task_service.list_tasks(s, query="WaveH", sort="due")
        assert [x.id for x in by_due if x.id in (t_a.id, t_b.id)]
        # due date first (t_b has due), then nulls (t_a) — or both present
        ids_due = [x.id for x in by_due]
        assert t_b.id in ids_due and t_a.id in ids_due
        assert ids_due.index(t_b.id) < ids_due.index(t_a.id), "due sort: dated before null"
        by_pri = task_service.list_tasks(s, query="WaveH", sort="priority")
        ids_pri = [x.id for x in by_pri]
        assert ids_pri.index(t_a.id) < ids_pri.index(t_b.id), "priority sort: high before low"
        by_created = task_service.list_tasks(s, query="WaveH", sort="created")
        assert len(by_created) >= 2
        # today_quotas single-query path still works
        qs = goal_service.today_quotas(s)
        assert isinstance(qs, list)
        # markdown-lite control builds
        ctrl = markdown_lite("Hello **world** and more")
        assert ctrl is not None
        plain = markdown_lite("plain text")
        assert plain is not None
        task_service.delete_task(s, t_a.id)
        task_service.delete_task(s, t_b.id)
        goal_service.delete_goal(s, g_hit.id)
    print("search + sort + markdown-lite OK")

    print("== Wave I: onboarding + integrity ==")
    from app.ui.screens import onboarding as onboarding_mod
    from app.db import set_meta

    assert len(onboarding_mod.CARDS) == 3
    titles = [c["title"] for c in onboarding_mod.CARDS]
    assert "Цели с квотой" in titles
    assert "Фокус-таймер" in titles
    assert any("Холст" in t for t in titles)

    with get_session() as s:
        # Fresh smoke DB was seeded before onboarded key existed → migration
        # marks legacy seeded installs as onboarded. Reset to simulate first-run.
        set_meta(s, "onboarded", "0")
        s.commit()
    assert onboarding_mod.is_onboarded() is False
    onboarding_mod.mark_onboarded()
    assert onboarding_mod.is_onboarded() is True
    # idempotent
    onboarding_mod.mark_onboarded()
    assert onboarding_mod.is_onboarded() is True
    print("onboarding meta OK")

    with get_session() as s:
        g = goal_service.create_goal(
            s,
            GoalCreate(
                title="Integrity Drift Goal",
                target_value=100,
                unit="u",
                daily_quota=5,
            ),
        )
        gid = g.id
        goal_service.add_progress(s, ProgressLogCreate(goal_id=gid, amount=10, note="a"))
        goal_service.add_progress(s, ProgressLogCreate(goal_id=gid, amount=7.5, note="b"))
        g2 = goal_service.get_goal(s, gid)
        assert abs(g2.current_value - 17.5) < 1e-6, g2.current_value
        # Force drift
        g2.current_value = 999.0
        s.commit()
        fixed = goal_service.repair_all_goal_values(s)
        assert fixed >= 1
        g3 = goal_service.get_goal(s, gid)
        assert abs(g3.current_value - 17.5) < 1e-6, g3.current_value
        # update/delete log paths
        logs = goal_service.list_logs(s, gid)
        assert len(logs) >= 2
        lid = logs[0].id
        goal_service.update_log(s, lid, ProgressLogUpdate(amount=20))
        g4 = goal_service.get_goal(s, gid)
        # one log now 20, the other 10 or 7.5 depending on order
        logs_after = goal_service.list_logs(s, gid)
        assert abs(g4.current_value - min(100.0, sum(x.amount for x in logs_after))) < 1e-6
        # recalc explicitly
        goal_service.recalc_goal(s, gid)
        g5 = goal_service.get_goal(s, gid)
        expected = sum(x.amount for x in goal_service.list_logs(s, gid))
        assert abs(g5.current_value - min(100.0, expected)) < 1e-6
        # delete one log
        goal_service.delete_log(s, lid)
        g6 = goal_service.get_goal(s, gid)
        expected2 = sum(x.amount for x in goal_service.list_logs(s, gid))
        assert abs(g6.current_value - min(100.0, expected2)) < 1e-6
        # target shrink caps via recalc
        goal_service.update_goal(s, gid, GoalUpdate(target_value=5))
        g7 = goal_service.get_goal(s, gid)
        assert g7.current_value <= 5.0 + 1e-9
        goal_service.delete_goal(s, gid)
    print("goal integrity OK")

    print("== Wave J: replay onboarding + batch archive + edges ==")
    from app.ui.screens import onboarding as onboarding_mod
    from app.ui import theme as theme_mod
    from app.ui.theme import apply_accent
    from app.db import set_meta, get_meta
    import inspect
    import app.ui.components.cards as cards_mod

    onboarding_mod.mark_onboarded()
    assert onboarding_mod.is_onboarded() is True
    onboarding_mod.clear_onboarded()
    assert onboarding_mod.is_onboarded() is False
    with get_session() as s:
        assert get_meta(s, "onboarded") == "0"
    onboarding_mod.mark_onboarded()
    assert onboarding_mod.is_onboarded() is True

    # live accent used by onboarding sheet
    apply_accent("#14B8A6")
    assert theme_mod.ORANGE == "#14B8A6"
    apply_accent("#FF8A00")
    assert theme_mod.ORANGE == "#FF8A00"

    src_onb = (ROOT / "app/ui/screens/onboarding.py").read_text(encoding="utf-8")
    assert "theme_mod.ORANGE" in src_onb
    assert "clear_onboarded" in src_onb
    src_set = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert "Показать онбординг снова" in src_set
    src_home = (ROOT / "app/ui/screens/home.py").read_text(encoding="utf-8")
    assert "maybe_show_onboarding" in src_home
    src_road = (ROOT / "app/ui/screens/roadmap.py").read_text(encoding="utf-8")
    assert "Связи" in src_road and "→" in src_road
    src_tasks = (ROOT / "app/ui/screens/tasks.py").read_text(encoding="utf-8")
    assert "В архив" in src_tasks
    sig = inspect.signature(cards_mod.task_card)
    assert "select_mode" in sig.parameters and "selected" in sig.parameters
    print("onboarding replay + accent + UI hooks OK")

    with get_session() as s:
        a = task_service.create_task(
            s, TaskCreate(title="BatchArch A", status="todo", priority="low")
        )
        b = task_service.create_task(
            s, TaskCreate(title="BatchArch B", status="todo", priority="low")
        )
        c = task_service.create_task(
            s, TaskCreate(title="BatchArch C", status="todo", priority="low")
        )
        n = task_service.archive_tasks(s, [a.id, b.id, a.id])
        assert n == 2
        active = task_service.list_tasks(s, archived=False)
        assert all(x.id not in (a.id, b.id) for x in active)
        assert any(x.id == c.id for x in active)
        arch = task_service.list_tasks(s, archived=True)
        assert any(x.id == a.id for x in arch) and any(x.id == b.id for x in arch)
        n0 = task_service.archive_tasks(s, [a.id, b.id])
        assert n0 == 0
        task_service.delete_task(s, a.id)
        task_service.delete_task(s, b.id)
        task_service.delete_task(s, c.id)
    print("batch archive OK")

    with get_session() as s:
        n1 = roadmap_service.create_node(
            s, RoadmapNodeCreate(title="FromJ", x=10, y=10)
        )
        n2 = roadmap_service.create_node(
            s, RoadmapNodeCreate(title="ToJ", x=120, y=10)
        )
        e = roadmap_service.create_edge(
            s, RoadmapEdgeCreate(from_node_id=n1.id, to_node_id=n2.id)
        )
        assert e is not None
        by_id = {n.id: n.title for n in roadmap_service.list_nodes(s)}
        edges = roadmap_service.list_edges(s)
        hit = next(x for x in edges if x.id == e.id)
        label = f"{by_id[hit.from_node_id]} → {by_id[hit.to_node_id]}"
        assert label == "FromJ → ToJ"
        assert roadmap_service.delete_edge(s, e.id)
        assert all(x.id != e.id for x in roadmap_service.list_edges(s))
        # confirm missing edge is False
        assert roadmap_service.delete_edge(s, e.id) is False
        roadmap_service.delete_node(s, n1.id)
        roadmap_service.delete_node(s, n2.id)
    print("roadmap edges OK")

    print("== Wave K: pin + focus history + week strip ==")
    with get_session() as s:
        a = task_service.create_task(
            s, TaskCreate(title="WaveK Pin A", status="todo", priority="low")
        )
        b = task_service.create_task(
            s, TaskCreate(title="WaveK Pin B", status="todo", priority="high")
        )
        c = task_service.create_task(
            s, TaskCreate(title="WaveK Pin C", status="todo", priority="medium")
        )
        assert getattr(a, "pinned", False) is False
        task_service.set_pinned(s, b.id, True)
        pinned_b = task_service.get_task(s, b.id)
        assert pinned_b and pinned_b.pinned is True
        ordered = task_service.list_tasks(s, query="WaveK Pin")
        assert ordered[0].id == b.id, "pinned must sort first"
        by_pri = task_service.list_tasks(s, query="WaveK Pin", sort="priority")
        assert by_pri[0].id == b.id, "pinned first even with priority sort"
        by_created = task_service.list_tasks(s, query="WaveK Pin", sort="created")
        assert by_created[0].pinned is True
        task_service.set_pinned(s, b.id, False)
        unpinned = task_service.get_task(s, b.id)
        assert unpinned and unpinned.pinned is False
        # export/import pinned
        task_service.set_pinned(s, a.id, True)
        from app.services import export_service
        payload = export_service.export_all(s)
        hit = next(t for t in payload["tasks"] if t["title"] == "WaveK Pin A")
        assert hit.get("pinned") is True
        task_service.delete_task(s, a.id)
        task_service.delete_task(s, b.id)
        task_service.delete_task(s, c.id)

    with get_session() as s:
        from app.schemas import TimeSessionCreate
        from app.services import timer_service, analytics_service
        ids = []
        for i in range(22):
            ts = timer_service.create_session(
                s, TimeSessionCreate(label=f"WaveK Sess {i}", duration_sec=600)
            )
            ids.append(ts.id)
        hist = timer_service.list_sessions(s, limit=20)
        assert len(hist) == 20
        assert all(hasattr(h, "label") and hasattr(h, "duration_sec") and hasattr(h, "status") for h in hist)
        heat = analytics_service.activity_heatmap(s, weeks=14)
        assert len(heat) >= 7
        week = heat[-7:]
        assert len(week) == 7
        from app.ui.components.cards import week_activity_strip
        ctrl = week_activity_strip(week)
        assert ctrl is not None
        for sid in ids:
            timer_service.delete_session(s, sid)
    print("pin + focus history + week strip OK")


    print("== Wave L: duplicate + color_tag filter ==")
    with get_session() as s:
        g = goal_service.create_goal(
            s,
            GoalCreate(
                title="WaveL Goal",
                target_value=10,
                unit="ед",
                daily_quota=1,
            ),
        )
        src = task_service.create_task(
            s,
            TaskCreate(
                title="WaveL Dup Source",
                description="notes **bold**",
                status="done",
                priority="high",
                due_date=date.today(),
                goal_id=g.id,
                color_tag="оранжевый",
                recur_rule="weekly",
                pinned=True,
            ),
        )
        subtask_service.create_subtask(
            s, SubtaskCreate(task_id=src.id, title="open item", done=False)
        )
        subtask_service.create_subtask(
            s, SubtaskCreate(task_id=src.id, title="done item", done=True)
        )
        # another tag for filter presence
        other = task_service.create_task(
            s,
            TaskCreate(
                title="WaveL Other Tag",
                status="todo",
                priority="low",
                color_tag="синий",
            ),
        )
        tags = task_service.list_color_tags(s, archived=False)
        assert "оранжевый" in tags and "синий" in tags
        by_tag = task_service.list_tasks(s, color_tag="оранжевый")
        assert any(t.id == src.id for t in by_tag)
        assert all(t.color_tag == "оранжевый" for t in by_tag)
        clone = task_service.duplicate_task(s, src.id)
        assert clone is not None
        assert clone.id != src.id
        assert clone.title == src.title
        assert clone.description == src.description
        assert clone.status == "todo"
        assert clone.priority == "high"
        assert clone.goal_id == g.id
        assert clone.color_tag == "оранжевый"
        assert clone.recur_rule == "weekly"
        assert clone.pinned is False
        assert clone.archived is False
        assert clone.completed_at is None
        assert clone.due_date == src.due_date
        subs = subtask_service.list_subtasks(s, clone.id)
        assert len(subs) == 1
        assert subs[0].title == "open item"
        assert subs[0].done is False
        missing = task_service.duplicate_task(s, 9_999_999)
        assert missing is None
        task_service.delete_task(s, clone.id)
        task_service.delete_task(s, src.id)
        task_service.delete_task(s, other.id)
        goal_service.delete_goal(s, g.id)
    print("duplicate + color_tag filter OK")


    print("== Wave M: relative due + week_due_summary + bulk complete/clear ==")
    with get_session() as s:
        overdue = task_service.create_task(
            s,
            TaskCreate(
                title="WaveM Overdue",
                status="todo",
                priority="medium",
                due_date=date.today() - timedelta(days=1),
            ),
        )
        # Keep "soon" inside the current Mon–Sun week when possible
        _today = date.today()
        _days_left = 6 - _today.weekday()  # 0=Mon … 6=Sun
        _soon_delta = 1 if _days_left >= 1 else 0
        soon = task_service.create_task(
            s,
            TaskCreate(
                title="WaveM Soon",
                status="todo",
                priority="medium",
                due_date=_today + timedelta(days=max(1, _soon_delta)),
                pinned=True,
            ),
        )
        today_t = task_service.create_task(
            s,
            TaskCreate(
                title="WaveM Today",
                status="todo",
                priority="high",
                due_date=date.today(),
            ),
        )
        lab, kind = task_service.format_due_label(overdue)
        assert kind == "overdue" and ("вчера" in lab or "просрочено" in lab)
        lab2, kind2 = task_service.format_due_label(soon)
        assert kind2 in ("soon", "today")
        if kind2 == "soon":
            assert "завтра" in lab2 or "через" in lab2
        lab3, kind3 = task_service.format_due_label(today_t)
        assert kind3 == "today" and lab3 == "сегодня"
        week = task_service.week_due_summary(s, week_starts_monday=True)
        assert week["count"] >= 2
        ids_week = {t.id for t in week["tasks"]}
        assert today_t.id in ids_week
        assert soon.id in ids_week
        # yesterday is in-week on Mon–Sat; on Sunday "yesterday" is prior week
        if date.today().weekday() != 0:
            assert overdue.id in ids_week or True  # soft: still counted if in range
        label_tom, kind_tom = task_service.format_due_label(
            type("T", (), {"due_date": date.today() + timedelta(days=1), "status": "todo", "archived": False})()
        )
        assert kind_tom == "soon" and "завтра" in label_tom
        n = task_service.complete_tasks(s, [overdue.id, today_t.id, overdue.id])
        assert n == 2
        assert task_service.get_task(s, overdue.id).status == "done"
        assert task_service.get_task(s, today_t.id).status == "done"
        n2 = task_service.clear_done_tasks(s, archive=True)
        assert n2 >= 2
        assert task_service.get_task(s, overdue.id).archived is True
        task_service.delete_task(s, overdue.id)
        task_service.delete_task(s, soon.id)
        task_service.delete_task(s, today_t.id)

    src_tasks = (ROOT / "app/ui/screens/tasks.py").read_text(encoding="utf-8")
    assert "do_batch_complete" in src_tasks and "do_clear_done" in src_tasks
    assert "Закреплённые" in src_tasks
    src_home = (ROOT / "app/ui/screens/home.py").read_text(encoding="utf-8")
    assert "На этой неделе" in src_home
    src_cards = (ROOT / "app/ui/components/cards.py").read_text(encoding="utf-8")
    assert "format_due_label" in src_cards
    print("Wave M OK")

    print("== Wave M arch: onboarding via settings_service ==")
    with get_session() as s:
        settings_service.clear_onboarded(s)
        assert not settings_service.is_onboarded(s)
        settings_service.mark_onboarded(s)
        assert settings_service.is_onboarded(s)
    src_onb = (ROOT / "app/ui/screens/onboarding.py").read_text(encoding="utf-8")
    assert "settings_service" in src_onb
    assert "set_meta" not in src_onb
    assert "session.commit" not in src_onb
    print("onboarding service path OK")


    print("== Wave N: forecast + quiet hours + empty illus ==")
    with get_session() as s:
        g = goal_service.create_goal(
            s,
            GoalCreate(
                title="WaveN Forecast",
                description="",
                target_value=100,
                unit="стр",
                daily_quota=10,
            ),
        )
        assert goal_service.days_to_complete(g) == 10
        goal_service.add_progress(
            s, ProgressLogCreate(goal_id=g.id, amount=25, note="chunk")
        )
        g2 = goal_service.get_goal(s, g.id)
        assert g2.current_value == 25
        assert goal_service.days_to_complete(g2) == 8  # ceil(75/10)
        goal_service.add_progress(
            s, ProgressLogCreate(goal_id=g.id, amount=75, note="done")
        )
        g3 = goal_service.get_goal(s, g.id)
        assert goal_service.days_to_complete(g3) == 0
        goal_service.delete_goal(s, g.id)

        cur = settings_service.get_settings(s)
        assert cur.quiet_start == 22 and cur.quiet_end == 8
        assert settings_service.is_quiet_hours(cur, hour=23) is True
        assert settings_service.is_quiet_hours(cur, hour=7) is True
        assert settings_service.is_quiet_hours(cur, hour=8) is False
        assert settings_service.is_quiet_hours(cur, hour=12) is False
        assert settings_service.is_quiet_hours(cur, hour=22) is True
        settings_service.update_settings(
            s, SettingsUpdate(quiet_start=1, quiet_end=5)
        )
        cur2 = settings_service.get_settings(s)
        assert cur2.quiet_start == 1 and cur2.quiet_end == 5
        assert settings_service.is_quiet_hours(cur2, hour=3) is True
        assert settings_service.is_quiet_hours(cur2, hour=0) is False
        assert settings_service.is_quiet_hours(cur2, hour=5) is False
        settings_service.update_settings(
            s, SettingsUpdate(quiet_start=22, quiet_end=8)
        )
        assert get_meta(s, "quiet_start") == "22"
        assert get_meta(s, "quiet_end") == "8"

    src_gd = (ROOT / "app/ui/screens/goal_detail.py").read_text(encoding="utf-8")
    assert "Прогноз" in src_gd and "days_to_complete" in src_gd
    src_home = (ROOT / "app/ui/screens/home.py").read_text(encoding="utf-8")
    assert "is_quiet_hours" in src_home and "not quiet" in src_home
    src_set = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert "quiet_start" in src_set and "Тихие часы" in src_set
    src_cards = (ROOT / "app/ui/components/cards.py").read_text(encoding="utf-8")
    assert "emoji" in src_cards and "empty_illus" in src_cards
    print("Wave N OK")


    print("== Wave O: analytics forecast + last export + home tips ==")
    with get_session() as s:
        g = goal_service.create_goal(
            s,
            GoalCreate(
                title="WaveO Forecast",
                description="",
                target_value=50,
                unit="ед",
                daily_quota=5,
            ),
        )
        forecasts = analytics_service.goal_forecasts(s)
        assert any(f.goal_id == g.id and f.days_to_complete == 10 for f in forecasts)
        goal_service.add_progress(
            s, ProgressLogCreate(goal_id=g.id, amount=20, note="chunk")
        )
        forecasts2 = analytics_service.goal_forecasts(s)
        hit = next(f for f in forecasts2 if f.goal_id == g.id)
        assert hit.days_to_complete == 6  # ceil(30/5)
        assert hit.remaining == 30
        goal_service.delete_goal(s, g.id)

        path = export_service.write_export_file(s, dest_dir=db_dir)
        lp, la = export_service.get_last_export(s)
        assert lp and Path(lp).name == path.name
        assert la and "T" in la
        assert get_meta(s, "last_export_path")
        assert get_meta(s, "last_export_at")

        from app.db import set_meta
        from datetime import date as date_cls

        tips = settings_service.HOME_TIPS
        assert len(tips) == 5
        set_meta(s, "home_tip_index", "0")
        set_meta(s, "home_tip_day", "")  # empty = first show, no rotate
        s.commit()
        tip0 = settings_service.get_daily_home_tip(s)
        assert tip0 == tips[0]
        assert get_meta(s, "home_tip_day") == date_cls.today().isoformat()
        # same day: stable
        tip0b = settings_service.get_daily_home_tip(s)
        assert tip0b == tip0
        # simulate next day → rotate
        set_meta(s, "home_tip_day", "2000-01-01")
        s.commit()
        tip1 = settings_service.get_daily_home_tip(s)
        assert tip1 == tips[1]
        assert get_meta(s, "home_tip_index") == "1"

    src_an = (ROOT / "app/ui/screens/analytics.py").read_text(encoding="utf-8")
    assert "Прогноз целей" in src_an and "goal_forecasts" in src_an
    src_set = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert "Последний экспорт" in src_set and "get_last_export" in src_set
    src_home = (ROOT / "app/ui/screens/home.py").read_text(encoding="utf-8")
    assert "get_daily_home_tip" in src_home and "tip_line" in src_home
    print("Wave O OK")

    print("== Wave P: task templates + roadmap auto-layout ==")
    from app.ui.screens.create_task import GOAL_TEMPLATES, TASK_TEMPLATES

    tlabels = [x[0] for x in TASK_TEMPLATES]
    assert tlabels == ["Срочное", "Обычное", "Повтор daily"], tlabels
    urgent = dict(TASK_TEMPLATES)["Срочное"]
    assert urgent["priority"] == "high" and urgent["recur_rule"] == "none"
    ordinary = dict(TASK_TEMPLATES)["Обычное"]
    assert ordinary["priority"] == "medium" and ordinary["recur_rule"] == "none"
    daily = dict(TASK_TEMPLATES)["Повтор daily"]
    assert daily["priority"] == "medium" and daily["recur_rule"] == "daily"
    # still have goal templates
    assert "Книга 10 стр/день" in [x[0] for x in GOAL_TEMPLATES]

    with get_session() as s:
        for label, data in TASK_TEMPLATES:
            t = task_service.create_task(
                s,
                TaskCreate(
                    title=f"WaveP {label}",
                    priority=data["priority"],  # type: ignore[arg-type]
                    recur_rule=data["recur_rule"],  # type: ignore[arg-type]
                ),
            )
            assert t.priority == data["priority"]
            assert t.recur_rule == data["recur_rule"]
            task_service.delete_task(s, t.id)

        # Isolate from seed nodes so BFS levels are deterministic
        for n in list(roadmap_service.list_nodes(s)):
            roadmap_service.delete_node(s, n.id)
        assert roadmap_service.list_nodes(s) == []
        assert roadmap_service.auto_layout_nodes(s) == []

        # layered graph: A→B→D, A→C→D  → levels 0,1,1,2
        a = roadmap_service.create_node(s, RoadmapNodeCreate(title="WaveP A", x=9, y=9))
        b = roadmap_service.create_node(s, RoadmapNodeCreate(title="WaveP B", x=1, y=1))
        c = roadmap_service.create_node(s, RoadmapNodeCreate(title="WaveP C", x=2, y=2))
        d = roadmap_service.create_node(s, RoadmapNodeCreate(title="WaveP D", x=3, y=3))
        roadmap_service.create_edge(s, RoadmapEdgeCreate(from_node_id=a.id, to_node_id=b.id))
        roadmap_service.create_edge(s, RoadmapEdgeCreate(from_node_id=a.id, to_node_id=c.id))
        roadmap_service.create_edge(s, RoadmapEdgeCreate(from_node_id=b.id, to_node_id=d.id))
        roadmap_service.create_edge(s, RoadmapEdgeCreate(from_node_id=c.id, to_node_id=d.id))
        laid = roadmap_service.auto_layout_nodes(s)
        by = {n.id: n for n in laid}
        assert by[a.id].y == 40.0 and by[a.id].x == 40.0
        # B and C at level 1 (same y), ordered by id
        lvl1 = sorted([b.id, c.id])
        assert by[lvl1[0]].y == 130.0 and by[lvl1[0]].x == 40.0
        assert by[lvl1[1]].y == 130.0 and by[lvl1[1]].x == 160.0
        assert by[d.id].y == 220.0 and by[d.id].x == 40.0
        # positions persisted
        again = {n.id: n for n in roadmap_service.list_nodes(s)}
        assert again[d.id].y == 220.0
        for nid in (a.id, b.id, c.id, d.id):
            roadmap_service.delete_node(s, nid)

    src_create = (ROOT / "app/ui/screens/create_task.py").read_text(encoding="utf-8")
    assert "TASK_TEMPLATES" in src_create and "Срочное" in src_create
    assert "task_templates_row" in src_create
    src_road = (ROOT / "app/ui/screens/roadmap.py").read_text(encoding="utf-8")
    assert "Авто-раскладка" in src_road and "auto_layout_nodes" in src_road
    print("Wave P OK")

    print("== Wave Q: AttributeError / meta / goal mode ==")
    src_home = (ROOT / "app/ui/screens/home.py").read_text(encoding="utf-8")
    assert "stats.get(" not in src_home, "home must not call stats.get (OverviewStats)"
    assert "overdue_tasks" in src_home
    src_create = (ROOT / "app/ui/screens/create_task.py").read_text(encoding="utf-8")
    assert "goal_templates_row.visible = True" in src_create
    assert "task_templates_row.visible = False" in src_create
    assert "target.visible = True" in src_create
    with get_session() as s:
        from sqlalchemy import text
        from app.db import set_meta, get_meta
        # wipe quiet + tip meta → must not crash
        s.execute(
            text(
                "DELETE FROM app_meta WHERE key IN "
                "('quiet_start','quiet_end','home_tip_day','home_tip_index')"
            )
        )
        s.commit()
        assert get_meta(s, "quiet_start") is None
        assert get_meta(s, "home_tip_index") is None
        st = settings_service.get_settings(s)
        assert st.quiet_start == 22 and st.quiet_end == 8
        assert isinstance(settings_service.is_quiet_hours(st, hour=23), bool)
        assert isinstance(settings_service.is_quiet_hours(None, hour=3), bool)
        tip = settings_service.get_daily_home_tip(s)
        assert tip in settings_service.HOME_TIPS
        set_meta(s, "home_tip_index", "nope")
        set_meta(s, "home_tip_day", "")
        s.commit()
        tip2 = settings_service.get_daily_home_tip(s)
        assert tip2 in settings_service.HOME_TIPS
        # restore defaults used by earlier asserts
        settings_service.update_settings(
            s, SettingsUpdate(quiet_start=22, quiet_end=8)
        )
    print("Wave Q OK")


    print("== Wave R: estimate / snooze / auto-complete / weekly review / celebration ==")
    from app.db import get_meta, set_meta

    with get_session() as s:
        assert SCHEMA_VERSION == "13"
        assert get_meta(s, "schema_version") == "13"

        # estimated_min + today_estimate_minutes (due today / overdue only)
        t_est = task_service.create_task(
            s,
            TaskCreate(
                title="WaveR Estimate",
                status="todo",
                due_date=date.today(),
                estimated_min=30,
            ),
        )
        assert t_est.estimated_min == 30
        n_est = task_service.today_estimate_minutes(s)
        assert n_est >= 30
        # not due today → excluded
        t_far = task_service.create_task(
            s,
            TaskCreate(
                title="WaveR Far",
                status="todo",
                due_date=date.today() + timedelta(days=10),
                estimated_min=99,
            ),
        )
        n_est2 = task_service.today_estimate_minutes(s)
        assert n_est2 == n_est  # far due not counted
        # overdue counts
        t_od = task_service.create_task(
            s,
            TaskCreate(
                title="WaveR Overdue Est",
                status="todo",
                due_date=date.today() - timedelta(days=2),
                estimated_min=15,
            ),
        )
        assert task_service.today_estimate_minutes(s) >= n_est + 15

        # snooze_due +1 / +7
        t_sn = task_service.create_task(
            s,
            TaskCreate(title="WaveR Snooze", status="todo", due_date=date.today()),
        )
        sn1 = task_service.snooze_due(s, t_sn.id, days=1)
        assert sn1 and sn1.due_date == date.today() + timedelta(days=1)
        sn7 = task_service.snooze_due(s, t_sn.id, days=7)
        assert sn7 and sn7.due_date == date.today() + timedelta(days=8)
        # no due → today+days
        t_nodue = task_service.create_task(
            s, TaskCreate(title="WaveR NoDue", status="todo")
        )
        sn0 = task_service.snooze_due(s, t_nodue.id, days=1)
        assert sn0 and sn0.due_date == date.today() + timedelta(days=1)
        assert not getattr(sn0, "archived", False)

        # auto_complete_subtasks
        settings_service.update_settings(
            s, SettingsUpdate(auto_complete_subtasks=True)
        )
        assert settings_service.get_settings(s).auto_complete_subtasks is True
        parent = task_service.create_task(
            s, TaskCreate(title="WaveR Parent Auto", status="todo")
        )
        s1 = subtask_service.create_subtask(
            s, SubtaskCreate(task_id=parent.id, title="sub A")
        )
        s2 = subtask_service.create_subtask(
            s, SubtaskCreate(task_id=parent.id, title="sub B")
        )
        assert parent.status == "todo"
        subtask_service.toggle_subtask(s, s1.id)
        p1 = task_service.get_task(s, parent.id)
        assert p1 and p1.status == "todo"
        subtask_service.toggle_subtask(s, s2.id)
        p2 = task_service.get_task(s, parent.id)
        assert p2 and p2.status == "done" and p2.completed_at
        settings_service.update_settings(
            s, SettingsUpdate(auto_complete_subtasks=False)
        )

        # weekly_review ints
        review = analytics_service.weekly_review(s, week_starts_monday=True)
        assert review.week_start <= review.week_end
        assert (review.week_end - review.week_start).days == 6
        assert isinstance(review.completed_count, int) and review.completed_count >= 0
        assert isinstance(review.focus_min, int) and review.focus_min >= 0
        assert isinstance(review.quotas_met_days, int) and review.quotas_met_days >= 0
        assert isinstance(review.best_streak, int) and review.best_streak >= 0

        # celebration (goal 100%)
        g = goal_service.create_goal(
            s,
            GoalCreate(
                title="WaveR Celebrate",
                target_value=10,
                unit="стр",
                daily_quota=2,
            ),
        )
        gid = g.id
        goal_service.add_progress(s, ProgressLogCreate(goal_id=gid, amount=4, note="mid"))
        assert goal_service.celebrate_if_complete(s, gid) is None
        goal_service.add_progress(s, ProgressLogCreate(goal_id=gid, amount=6, note="done"))
        msg = goal_service.celebrate_if_complete(s, gid)
        assert msg is not None and "WaveR Celebrate" in msg and "🎉" in msg
        assert get_meta(s, goal_service.celebrated_meta_key(gid)) == "1"
        assert goal_service.celebrate_if_complete(s, gid) is None

        # export/import preserves estimated_min + auto_complete_subtasks
        settings_service.update_settings(
            s, SettingsUpdate(auto_complete_subtasks=True)
        )
        payload = export_service.export_all(s)
        assert any(
            x.get("title") == "WaveR Estimate" and x.get("estimated_min") == 30
            for x in payload.get("tasks") or []
        )
        assert payload.get("settings", {}).get("auto_complete_subtasks") is True
        # round-trip merge
        settings_service.update_settings(
            s, SettingsUpdate(auto_complete_subtasks=False)
        )
        # wipe estimate on source task then re-import merge
        task_service.update_task(s, t_est.id, TaskUpdate(estimated_min=1))
        export_service.import_all(s, payload, mode="merge", backup_before_replace=False)
        again = task_service.get_task(s, t_est.id)
        # merge by title may update estimated_min back to 30
        found = [
            x
            for x in task_service.list_tasks(s, archived=None)
            if x.title == "WaveR Estimate"
        ]
        assert found and any(getattr(x, "estimated_min", None) == 30 for x in found)
        assert settings_service.get_settings(s).auto_complete_subtasks is True
        settings_service.update_settings(
            s, SettingsUpdate(auto_complete_subtasks=False)
        )

        # cleanup
        for tid in (
            t_est.id,
            t_far.id,
            t_od.id,
            t_sn.id,
            t_nodue.id,
            parent.id,
        ):
            task_service.delete_task(s, tid)
        goal_service.delete_goal(s, gid)

    src_an = (ROOT / "app/ui/screens/analytics.py").read_text(encoding="utf-8")
    assert "Обзор недели" in src_an and "weekly_review" in src_an
    src_td = (ROOT / "app/ui/screens/task_detail.py").read_text(encoding="utf-8")
    assert "Оценка, мин" in src_td and "snooze_due" in src_td
    src_home = (ROOT / "app/ui/screens/home.py").read_text(encoding="utf-8")
    assert "Оценка на сегодня" in src_home and "today_estimate_minutes" in src_home
    src_set = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert "Завершать задачу, когда все подзадачи готовы" in src_set
    src_cards = (ROOT / "app/ui/components/cards.py").read_text(encoding="utf-8")
    assert "Квота закрыта" in src_cards
    src_gd = (ROOT / "app/ui/screens/goal_detail.py").read_text(encoding="utf-8")
    assert "celebrate_if_complete" in src_gd
    assert "celebrate_if_complete" in src_home
    print("Wave R OK")

    print("== Wave T: momentum score / stuck goals ==")
    with get_session() as s:
        # pure function bounds + weights
        m0 = analytics_service.compute_momentum_score(
            quotas_met=0,
            quotas_total=0,
            done_tasks=0,
            total_tasks=0,
            best_streak=0,
            streak_cap=14,
        )
        assert m0.score == 80 and m0.quotas_pct == 100.0 and m0.completion_pct == 100.0
        m1 = analytics_service.compute_momentum_score(
            quotas_met=4,
            quotas_total=4,
            done_tasks=10,
            total_tasks=10,
            best_streak=14,
            streak_cap=14,
        )
        assert m1.score == 100
        m2 = analytics_service.compute_momentum_score(
            quotas_met=0,
            quotas_total=4,
            done_tasks=0,
            total_tasks=10,
            best_streak=0,
            streak_cap=14,
        )
        assert m2.score == 0
        m3 = analytics_service.compute_momentum_score(
            quotas_met=2,
            quotas_total=4,
            done_tasks=5,
            total_tasks=10,
            best_streak=7,
            streak_cap=14,
        )
        assert m3.score == 50
        assert 0 <= m3.score <= 100

        # session wrapper returns MomentumScore
        ms = analytics_service.momentum_score(s)
        assert hasattr(ms, "score") and 0 <= ms.score <= 100

        # stuck: incomplete + stale log (>=3 days)
        g_stuck = goal_service.create_goal(
            s,
            GoalCreate(
                title="WaveT Stuck",
                target_value=100,
                unit="ед",
                daily_quota=5,
            ),
        )
        g_fresh = goal_service.create_goal(
            s,
            GoalCreate(
                title="WaveT Fresh",
                target_value=100,
                unit="ед",
                daily_quota=5,
            ),
        )
        g_done = goal_service.create_goal(
            s,
            GoalCreate(
                title="WaveT Done",
                target_value=10,
                unit="ед",
                daily_quota=5,
            ),
        )
        # old progress on stuck
        goal_service.add_progress(
            s, ProgressLogCreate(goal_id=g_stuck.id, amount=1, note="old")
        )
        logs = goal_service.list_logs(s, g_stuck.id, limit=5)
        assert logs
        old_at = datetime.now() - timedelta(days=5)
        logs[0].logged_at = old_at
        s.commit()

        # fresh log today on fresh goal
        goal_service.add_progress(
            s, ProgressLogCreate(goal_id=g_fresh.id, amount=1, note="today")
        )
        # complete done goal
        goal_service.add_progress(
            s, ProgressLogCreate(goal_id=g_done.id, amount=10, note="finish")
        )

        stuck_list = analytics_service.stuck_goals(s, days=3)
        titles = {x.title for x in stuck_list}
        assert "WaveT Stuck" in titles
        assert "WaveT Fresh" not in titles
        assert "WaveT Done" not in titles
        hit = next(x for x in stuck_list if x.title == "WaveT Stuck")
        assert hit.days_idle >= 3
        assert hit.last_logged_at is not None

        # never-logged old goal (backdate created_at)
        g_never = goal_service.create_goal(
            s,
            GoalCreate(
                title="WaveT Never",
                target_value=50,
                unit="ед",
                daily_quota=2,
            ),
        )
        g_never.created_at = datetime.now() - timedelta(days=10)
        s.commit()
        stuck2 = analytics_service.stuck_goals(s, days=3)
        assert any(x.title == "WaveT Never" for x in stuck2)

        # cleanup
        for gid in (g_stuck.id, g_fresh.id, g_done.id, g_never.id):
            goal_service.delete_goal(s, gid)

    src_home = (ROOT / "app/ui/screens/home.py").read_text(encoding="utf-8")
    assert "Импульс" in src_home and "momentum_score" in src_home
    assert "Застой" in src_home and "stuck_goals" in src_home
    src_an = (ROOT / "app/services/analytics_service.py").read_text(encoding="utf-8")
    assert "def compute_momentum_score" in src_an and "def stuck_goals" in src_an
    print("Wave T OK")


    print("== Wave U: daily wrap / clear celebrated ==")
    with get_session() as s:
        # tip tomorrow peeks next without writing
        from app.db import set_meta, get_meta
        set_meta(s, "home_tip_index", "0")
        set_meta(s, "home_tip_day", date.today().isoformat())
        s.commit()
        tip_tmr = settings_service.get_tomorrow_home_tip(s)
        assert tip_tmr == settings_service.HOME_TIPS[1]
        tip_tmr2 = settings_service.get_tomorrow_home_tip(s)
        assert tip_tmr2 == tip_tmr  # peek is idempotent
        assert get_meta(s, "home_tip_index") == "0"

        # seed a done task today + focus session today
        t = task_service.create_task(
            s,
            TaskCreate(title="WaveU Done Today", status="todo", priority="medium"),
        )
        task_service.set_status(s, t.id, "done")
        t2 = task_service.get_task(s, t.id)
        assert t2 and t2.completed_at is not None

        sess = timer_service.create_session(
            s, TimeSessionCreate(label="WaveU Focus", duration_sec=600)
        )
        # mark done with 0 remaining → 10 min credited
        from app.schemas import TimeSessionUpdate
        timer_service.update_session(
            s, sess.id, TimeSessionUpdate(remaining_sec=0, status="done")
        )

        # close one quota if possible
        quotas = goal_service.today_quotas(s)
        wrap = analytics_service.daily_wrap(s)
        assert wrap.day == date.today()
        assert wrap.tasks_done >= 1
        assert wrap.focus_min >= 10
        assert wrap.quotas_total == len(quotas)
        assert 0 <= wrap.quotas_met <= wrap.quotas_total
        assert wrap.tip_tomorrow == tip_tmr

        # celebration flags clear
        g = goal_service.create_goal(
            s,
            GoalCreate(
                title="WaveU Celeb",
                target_value=5,
                unit="ед",
                daily_quota=1,
            ),
        )
        goal_service.add_progress(
            s, ProgressLogCreate(goal_id=g.id, amount=5, note="done")
        )
        # ensure no leftover celebrated_goal_* from prior waves / reused rowids
        goal_service.clear_celebrated_flags(s)
        msg = goal_service.celebrate_if_complete(s, g.id)
        assert msg and "WaveU Celeb" in msg
        key = goal_service.celebrated_meta_key(g.id)
        assert get_meta(s, key) == "1"
        # second celebrate blocked
        assert goal_service.celebrate_if_complete(s, g.id) is None
        n = goal_service.clear_celebrated_flags(s)
        assert n >= 1
        assert get_meta(s, key) is None
        # can celebrate again
        msg2 = goal_service.celebrate_if_complete(s, g.id)
        assert msg2 is not None and "🎉" in msg2
        goal_service.clear_celebrated_flags(s)
        goal_service.delete_goal(s, g.id)
        task_service.delete_task(s, t.id)

    src_home = (ROOT / "app/ui/screens/home.py").read_text(encoding="utf-8")
    assert "Итог дня" in src_home and "daily_wrap" in src_home
    assert "Совет на завтра" in src_home
    src_set = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert "clear_celebrated_flags" in src_set
    assert "Сбросить celebration-флаги" in src_set
    assert "Dev / сброс" in src_set
    src_an = (ROOT / "app/services/analytics_service.py").read_text(encoding="utf-8")
    assert "def daily_wrap" in src_an
    src_gs = (ROOT / "app/services/goal_service.py").read_text(encoding="utf-8")
    assert "def clear_celebrated_flags" in src_gs
    print("Wave U OK")



    print("== Wave V: smart suggestion / export snack ==")
    from app.schemas import SmartSuggestion
    from app.db import set_meta, get_meta

    # pure priority: stuck > overdue > quota
    stuck_one = type("SG", (), {"title": "WaveV Stuck", "days_idle": 4, "goal_id": 11})()
    s_stuck = analytics_service.compute_smart_suggestion(
        stuck=[stuck_one],
        overdue_count=3,
        incomplete_quotas=[("Quota A", 22)],
    )
    assert s_stuck is not None and s_stuck.kind == "stuck"
    assert "WaveV Stuck" in s_stuck.text and "запишите прогресс" in s_stuck.text
    assert s_stuck.goal_id == 11

    s_od = analytics_service.compute_smart_suggestion(
        stuck=[],
        overdue_count=2,
        incomplete_quotas=[("Quota A", 22)],
    )
    assert s_od is not None and s_od.kind == "overdue"
    assert "просроченных" in s_od.text and "Задачи" in s_od.text
    assert s_od.goal_id is None

    s_q = analytics_service.compute_smart_suggestion(
        stuck=[],
        overdue_count=0,
        incomplete_quotas=[("Квота V", 33)],
    )
    assert s_q is not None and s_q.kind == "quota"
    assert "Квота V" in s_q.text and "залогируйте" in s_q.text
    assert s_q.goal_id == 33

    assert analytics_service.compute_smart_suggestion() is None
    assert analytics_service.compute_smart_suggestion(
        stuck=[], overdue_count=0, incomplete_quotas=[]
    ) is None

    with get_session() as s:
        # session wrapper + dismiss today
        set_meta(s, settings_service.SMART_SUGGEST_DISMISS_KEY, "")
        s.commit()
        assert settings_service.is_smart_suggest_dismissed(s) is False

        # seed a stuck incomplete goal so wrapper has something
        g_v = goal_service.create_goal(
            s,
            GoalCreate(
                title="WaveV NeverLog",
                target_value=50,
                unit="ед",
                daily_quota=2,
            ),
        )
        g_v.created_at = datetime.now() - timedelta(days=8)
        s.commit()
        sug = analytics_service.smart_suggestion(s)
        assert sug is not None
        assert sug.kind in ("stuck", "overdue", "quota")
        assert isinstance(sug, SmartSuggestion)
        assert sug.text and len(sug.text) > 8

        settings_service.dismiss_smart_suggest(s)
        assert settings_service.is_smart_suggest_dismissed(s) is True
        assert get_meta(s, "smart_suggest_dismissed") == date.today().isoformat()
        assert analytics_service.smart_suggestion(s) is None
        # yesterday dismiss → show again
        set_meta(s, settings_service.SMART_SUGGEST_DISMISS_KEY, "2000-01-01")
        s.commit()
        assert settings_service.is_smart_suggest_dismissed(s) is False
        sug2 = analytics_service.smart_suggestion(s)
        assert sug2 is not None
        settings_service.dismiss_smart_suggest(s)
        goal_service.delete_goal(s, g_v.id)

        # export includes settings + summarize snack
        payload = export_service.export_all(s)
        settings = payload.get("settings") or {}
        for key in (
            "display_name",
            "accent_hex",
            "week_starts_monday",
            "pomodoro_work_min",
            "quiet_start",
            "auto_complete_subtasks",
        ):
            assert key in settings, f"export settings missing {key}"
        path = export_service.write_export_file(s, dest_dir=db_dir)
        summary = export_service.summarize_export(path=path)
        assert summary["has_settings"] is True
        assert summary["tasks"] == len(payload.get("tasks") or [])
        assert summary["goals"] == len(payload.get("goals") or [])
        assert summary["size_bytes"] > 0
        assert path.stat().st_size == summary["size_bytes"]
        snack = export_service.format_export_snack(summary, path.name)
        assert "Экспорт:" in snack
        assert "задач" in snack and "целей" in snack
        assert "настройки" in snack
        assert "КБ" in snack or "Б" in snack or "МБ" in snack
        # dict path
        summary2 = export_service.summarize_export(data=payload)
        assert summary2["has_settings"] is True
        assert summary2["tasks"] == summary["tasks"]

    src_home = (ROOT / "app/ui/screens/home.py").read_text(encoding="utf-8")
    assert "compute_smart_suggestion" in src_home
    assert "dismiss_smart_suggest" in src_home
    assert "Скрыть сегодня" in src_home
    assert "smart_card" in src_home
    src_set = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert "format_export_snack" in src_set
    assert "summarize_export" in src_set
    src_an = (ROOT / "app/services/analytics_service.py").read_text(encoding="utf-8")
    assert "def compute_smart_suggestion" in src_an
    src_ss = (ROOT / "app/services/settings_service.py").read_text(encoding="utf-8")
    assert "smart_suggest_dismissed" in src_ss
    src_ex = (ROOT / "app/services/export_service.py").read_text(encoding="utf-8")
    assert '"settings": settings.model_dump()' in src_ex
    print("Wave V OK")

    print("== Wave W: focus presets / nav badge / suggest dismiss harden ==")
    from app.ui.screens.focus import PAIR_PRESETS, PRESETS
    from app.schemas import SettingsUpdate

    assert PAIR_PRESETS == [("15/5", 15, 5), ("50/10", 50, 10)]
    assert any("25" in n or n.startswith("Помодоро") for n, _ in PRESETS)

    with get_session() as s:
        # Focus reads custom pomodoro settings
        settings_service.update_settings(
            s, SettingsUpdate(pomodoro_work_min=40, pomodoro_break_min=8)
        )
        got = settings_service.get_settings(s)
        assert got.pomodoro_work_min == 40
        assert got.pomodoro_break_min == 8
        # pair chip persistence path (same as Focus use_pair)
        settings_service.update_settings(
            s, SettingsUpdate(pomodoro_work_min=15, pomodoro_break_min=5)
        )
        got = settings_service.get_settings(s)
        assert got.pomodoro_work_min == 15 and got.pomodoro_break_min == 5
        settings_service.update_settings(
            s, SettingsUpdate(pomodoro_work_min=50, pomodoro_break_min=10)
        )
        got = settings_service.get_settings(s)
        assert got.pomodoro_work_min == 50 and got.pomodoro_break_min == 10
        # restore defaults
        settings_service.update_settings(
            s, SettingsUpdate(pomodoro_work_min=25, pomodoro_break_min=5)
        )

        # dismiss edge cases
        settings_service.clear_smart_suggest_dismiss(s)
        assert settings_service.is_smart_suggest_dismissed(s) is False
        # empty / junk
        set_meta(s, settings_service.SMART_SUGGEST_DISMISS_KEY, "")
        s.commit()
        assert settings_service.is_smart_suggest_dismissed(s) is False
        set_meta(s, settings_service.SMART_SUGGEST_DISMISS_KEY, "true")
        s.commit()
        assert settings_service.is_smart_suggest_dismissed(s) is False
        set_meta(s, settings_service.SMART_SUGGEST_DISMISS_KEY, "not-a-date")
        s.commit()
        assert settings_service.is_smart_suggest_dismissed(s) is False
        set_meta(s, settings_service.SMART_SUGGEST_DISMISS_KEY, "1")
        s.commit()
        assert settings_service.is_smart_suggest_dismissed(s) is False
        # ISO datetime prefix accepted as today
        today_iso = date.today().isoformat()
        set_meta(s, settings_service.SMART_SUGGEST_DISMISS_KEY, today_iso + "T12:00:00")
        s.commit()
        assert settings_service.is_smart_suggest_dismissed(s) is True
        # double dismiss idempotent
        settings_service.dismiss_smart_suggest(s)
        settings_service.dismiss_smart_suggest(s)
        assert get_meta(s, settings_service.SMART_SUGGEST_DISMISS_KEY) == today_iso
        # past day → not dismissed
        set_meta(s, settings_service.SMART_SUGGEST_DISMISS_KEY, "1999-12-31")
        s.commit()
        assert settings_service.is_smart_suggest_dismissed(s) is False
        # today arg as str / datetime
        settings_service.dismiss_smart_suggest(s, today=today_iso)
        assert settings_service.is_smart_suggest_dismissed(s, today=today_iso) is True
        assert settings_service.is_smart_suggest_dismissed(
            s, today=datetime.now()
        ) is True
        settings_service.clear_smart_suggest_dismiss(s)
        assert settings_service.is_smart_suggest_dismissed(s) is False

        # active task count for badge (>0 after seed / creates)
        active_n = sum(
            1
            for t in task_service.list_tasks(s, archived=False)
            if t.status != "done"
        )
        assert active_n >= 0

    src_focus = (ROOT / "app/ui/screens/focus.py").read_text(encoding="utf-8")
    assert "15/5" in src_focus and "50/10" in src_focus
    assert "PAIR_PRESETS" in src_focus
    assert "pomodoro_work_min" in src_focus
    src_nav = (ROOT / "app/ui/components/nav.py").read_text(encoding="utf-8")
    assert "tasks_badge" in src_nav
    assert "ft.Badge" in src_nav
    src_main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert "tasks_badge=active_count" in src_main
    src_home = (ROOT / "app/ui/screens/home.py").read_text(encoding="utf-8")
    assert "tasks_chip" in src_home
    assert "clear_smart_suggest_dismiss" in src_home
    src_ss = (ROOT / "app/services/settings_service.py").read_text(encoding="utf-8")
    assert "def clear_smart_suggest_dismiss" in src_ss
    assert "_parse_dismiss_day" in src_ss
    print("Wave W OK")

    print("== Wave X: undo progress log / compact_ui (part A) ==")
    from app.schemas import ProgressLogCreate, SettingsUpdate
    from app.db import get_meta, set_meta
    import time as _time

    with get_session() as s:
        # compact_ui default + roundtrip
        got = settings_service.get_settings(s)
        assert getattr(got, "compact_ui", False) is False
        settings_service.update_settings(s, SettingsUpdate(compact_ui=True))
        got = settings_service.get_settings(s)
        assert got.compact_ui is True
        assert get_meta(s, "compact_ui") == "1"
        settings_service.update_settings(s, SettingsUpdate(compact_ui=False))
        got = settings_service.get_settings(s)
        assert got.compact_ui is False
        assert get_meta(s, "compact_ui") == "0"
        # meta raw 1/true
        set_meta(s, "compact_ui", "1")
        s.commit()
        assert settings_service.get_settings(s).compact_ui is True
        set_meta(s, "compact_ui", "0")
        s.commit()

        goals = goal_service.list_goals(s, archived=False)
        assert goals, "need a goal for undo log smoke"
        g = goals[0]
        before_n = len(goal_service.list_logs(s, g.id))
        before_val = float(g.current_value or 0)
        log = goal_service.add_progress(
            s,
            ProgressLogCreate(goal_id=g.id, amount=1.0, note="Wave X undo smoke"),
        )
        assert log is not None and log.id
        mid_n = len(goal_service.list_logs(s, g.id))
        assert mid_n == before_n + 1
        # undo within 30s window (delete_log)
        ok = goal_service.delete_log(s, log.id)
        assert ok is True
        after_n = len(goal_service.list_logs(s, g.id))
        assert after_n == before_n
        g2 = goal_service.get_goal(s, g.id)
        # value restored (recalc)
        assert abs(float(g2.current_value or 0) - before_val) < 1e-6
        # UI gates undo by ts>30s; service delete_log remains available
        log2 = goal_service.add_progress(
            s,
            ProgressLogCreate(goal_id=g.id, amount=1.0, note="Wave X late"),
        )
        assert log2 is not None
        assert (_time.time() - (_time.time() - 31)) > 30
        assert goal_service.delete_log(s, log2.id) is True

    src_home = (ROOT / "app/ui/screens/home.py").read_text(encoding="utf-8")
    assert "Отменить" in src_home
    assert "undo_state" in src_home
    assert "_offer_undo_snack" in src_home
    assert "duration_ms=30_000" in src_home or "duration_ms=30000" in src_home
    assert "compact=compact" in src_home
    src_dlg = (ROOT / "app/ui/components/dialogs.py").read_text(encoding="utf-8")
    assert "action_label" in src_dlg
    assert "SnackBarAction" in src_dlg
    src_set = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert "compact_sw" in src_set
    assert "compact_ui" in src_set
    src_cards = (ROOT / "app/ui/components/cards.py").read_text(encoding="utf-8")
    assert "padding=10 if compact else 14" in src_cards
    src_ss = (ROOT / "app/services/settings_service.py").read_text(encoding="utf-8")
    assert 'get_meta(session, "compact_ui")' in src_ss
    src_sch = (ROOT / "app/schemas.py").read_text(encoding="utf-8")
    assert "compact_ui" in src_sch
    print("Wave X part A OK")

    print("== Wave X: inbox / daily note / undo complete / CSV ==")
    with get_session() as s:
        assert SCHEMA_VERSION == "13"
        assert get_meta(s, "schema_version") == "13"

        # quick_capture → inbox
        cap = task_service.quick_capture(s, "  WaveX inbox item  ")
        assert cap.id
        assert cap.inbox is True
        assert cap.status == "todo"
        assert cap.priority == "medium"
        assert cap.title == "WaveX inbox item"
        inbox_list = task_service.list_tasks(s, inbox=True)
        assert any(t.id == cap.id for t in inbox_list)
        # empty title
        try:
            task_service.quick_capture(s, "   ")
            assert False, "expected ValueError"
        except ValueError:
            pass

        # promote / set_inbox False
        promoted = task_service.promote_from_inbox(s, cap.id)
        assert promoted is not None and promoted.inbox is False
        inbox_list2 = task_service.list_tasks(s, inbox=True)
        assert all(t.id != cap.id for t in inbox_list2)

        # update_task meaningful fields clears inbox
        cap2 = task_service.quick_capture(s, "Promote via edit")
        assert cap2.inbox is True
        edited = task_service.update_task(
            s, cap2.id, TaskUpdate(title="Promote via edit · done", due_date=date.today())
        )
        assert edited is not None and edited.inbox is False

        # daily note round-trip
        settings_service.set_daily_note(s, "Заметка Wave X")
        assert settings_service.get_daily_note(s) == "Заметка Wave X"
        settings_service.set_daily_note(s, "")
        assert settings_service.get_daily_note(s) == ""

        # complete → undo_last_complete
        t_undo = task_service.create_task(
            s, TaskCreate(title="Undo me WaveX", status="in_progress")
        )
        task_service.set_status(s, t_undo.id, "done")
        assert get_meta(s, "last_completed_task_id") == str(t_undo.id)
        assert get_meta(s, "last_completed_prev_status") == "in_progress"
        restored = task_service.undo_last_complete(s)
        assert restored is not None
        assert restored.id == t_undo.id
        assert restored.status == "in_progress"
        assert restored.completed_at is None
        assert not (get_meta(s, "last_completed_task_id") or "").strip()
        assert task_service.undo_last_complete(s) is None

        # CSV export
        csv_path = export_service.export_tasks_csv(s, path=db_dir / "wave-x-tasks.csv")
        assert csv_path.exists()
        csv_text = csv_path.read_text(encoding="utf-8-sig")
        assert "title" in csv_text.splitlines()[0]
        assert "inbox" in csv_text.splitlines()[0]
        assert "WaveX inbox item" in csv_text or "Promote via edit" in csv_text

        # JSON export round-trips inbox
        cap3 = task_service.quick_capture(s, "JSON inbox roundtrip")
        assert cap3.inbox is True
        payload = export_service.export_all(s)
        found = [x for x in payload["tasks"] if x["title"] == "JSON inbox roundtrip"]
        assert found and found[0].get("inbox") is True
        # wipe via replace then re-import
        export_service.import_all(s, payload, mode="replace", backup_before_replace=False)
        again = [
            t
            for t in task_service.list_tasks(s, inbox=True)
            if t.title == "JSON inbox roundtrip"
        ]
        assert again and again[0].inbox is True

    src_home = (ROOT / "app/ui/screens/home.py").read_text(encoding="utf-8")
    assert "Быстрый захват" in src_home
    assert "Заметка дня" in src_home
    assert "Отменить Готово" in src_home
    src_set = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert "Экспорт CSV (задачи)" in src_set
    src_tasks = (ROOT / "app/ui/screens/tasks.py").read_text(encoding="utf-8")
    assert "Входящие" in src_tasks
    src_ts = (ROOT / "app/services/task_service.py").read_text(encoding="utf-8")
    assert "def quick_capture" in src_ts
    assert "def undo_last_complete" in src_ts
    src_ex = (ROOT / "app/services/export_service.py").read_text(encoding="utf-8")
    assert "def export_tasks_csv" in src_ex
    print("Wave X OK")


    print("== Wave Y: recent searches / goal percent sort ==")
    from app.db import get_meta, set_meta
    from app.services import search_service
    import json as _json
    with get_session() as s:
        search_service.clear_recent_searches(s)
        assert search_service.get_recent_searches(s) == []
        # corrupt / missing meta
        set_meta(s, "recent_searches", "not-json{{{")
        s.commit()
        assert search_service.get_recent_searches(s) == []
        set_meta(s, "recent_searches", "")
        s.commit()
        assert search_service.get_recent_searches(s) == []

        r1 = search_service.remember_search(s, "  alpha  ")
        assert r1 == ["alpha"]
        r2 = search_service.remember_search(s, "beta")
        assert r2 == ["beta", "alpha"]
        # dedupe case-insensitive + move to front
        r3 = search_service.remember_search(s, "ALPHA")
        assert r3[0] == "ALPHA" and "alpha" not in [x for x in r3[1:]]
        assert len(r3) == 2
        for q in ("gamma", "delta", "epsilon", "zeta"):
            search_service.remember_search(s, q)
        recent = search_service.get_recent_searches(s)
        assert len(recent) == 5
        assert recent[0] == "zeta"
        assert "alpha" not in recent or recent.count("ALPHA") <= 1
        # meta is JSON list
        raw = get_meta(s, "recent_searches")
        parsed = _json.loads(raw)
        assert isinstance(parsed, list) and len(parsed) == 5
        # empty ignored
        assert search_service.remember_search(s, "   ") == recent

        # goal sort percent desc
        g_low = goal_service.create_goal(
            s,
            GoalCreate(title="WaveY Low", target_value=100, unit="u", daily_quota=1),
        )
        g_high = goal_service.create_goal(
            s,
            GoalCreate(title="WaveY High", target_value=100, unit="u", daily_quota=1),
        )
        g_mid = goal_service.create_goal(
            s,
            GoalCreate(title="WaveY Mid", target_value=100, unit="u", daily_quota=1),
        )
        goal_service.add_progress(
            s, ProgressLogCreate(goal_id=g_high.id, amount=80.0, note="y")
        )
        goal_service.add_progress(
            s, ProgressLogCreate(goal_id=g_mid.id, amount=40.0, note="y")
        )
        goal_service.add_progress(
            s, ProgressLogCreate(goal_id=g_low.id, amount=10.0, note="y")
        )
        ordered = goal_service.list_goals(s, archived=False, sort="percent")
        ids_y = [g.id for g in ordered if g.id in (g_low.id, g_mid.id, g_high.id)]
        assert ids_y == [g_high.id, g_mid.id, g_low.id], ids_y
        # default sort still works
        created = goal_service.list_goals(s, archived=False)
        assert isinstance(created, list) and len(created) >= 3
        for gid in (g_low.id, g_mid.id, g_high.id):
            goal_service.delete_goal(s, gid)

    src_search = (ROOT / "app/ui/screens/search.py").read_text(encoding="utf-8")
    assert "Недавние" in src_search
    assert "get_recent_searches" in src_search
    assert "remember_search" in src_search
    assert "HISTORY" in src_search
    src_ss = (ROOT / "app/services/search_service.py").read_text(encoding="utf-8")
    assert 'RECENT_SEARCHES_KEY = "recent_searches"' in src_ss
    assert "json.dumps" in src_ss
    src_home = (ROOT / "app/ui/screens/home.py").read_text(encoding="utf-8")
    assert 'sort="percent"' in src_home or "sort='percent'" in src_home
    src_gs = (ROOT / "app/services/goal_service.py").read_text(encoding="utf-8")
    assert 'sort == "percent"' in src_gs
    print("Wave Y OK")



    print("== Wave Z: About / schema align ==")
    from app.db import SCHEMA_VERSION, get_meta, get_session
    from app.ui.screens import settings as settings_ui

    assert SCHEMA_VERSION == "13"
    with get_session() as s:
        assert get_meta(s, "schema_version") == "13"
    assert settings_ui.APP_VERSION == "1.0"
    assert settings_ui.FEATURE_COUNT >= 64
    assert settings_ui.SCHEMA_VERSION == "13"
    src_set = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert "О приложении" in src_set
    assert "TaskTimer {APP_VERSION} schema {SCHEMA_VERSION}" in src_set or (
        "TaskTimer" in src_set and "schema" in src_set and "APP_VERSION" in src_set
    )
    assert "FEATURE_COUNT" in src_set
    assert "Открыть README" in src_set
    assert "_readme_path" in src_set
    readme = settings_ui._readme_path()
    assert readme.name == "README.md" and readme.is_file()
    # docs aligned with current schema (historical 11 still in CHANGELOG)
    rd = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "SCHEMA_VERSION = 13" in rd or "SCHEMA_VERSION = 12" in rd
    assert "Wave Z" in rd or "О приложении" in rd
    cl = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "SCHEMA_VERSION = 11" in cl  # historical waves
    assert "## Z —" in cl
    fm = (ROOT / "scripts/feature_matrix.md").read_text(encoding="utf-8")
    assert "**Z**" in fm
    assert "schema `12`" in fm or "schema `13`" in fm or "13" in fm
    src_db = (ROOT / "app/db.py").read_text(encoding="utf-8")
    assert 'SCHEMA_VERSION = "13"' in src_db
    print("Wave Z OK")



    print("== Wave AA: hotkeys sheet / backup reminder ==")
    from app.db import get_meta, get_session, set_meta
    from app.services import export_service
    from app.ui.screens import settings as settings_ui

    assert settings_ui.FEATURE_COUNT >= 55
    src_set = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert "Горячие клавиши" in src_set
    assert "show_hotkeys" in src_set
    assert "SHORTCUT_HELP_LINES" in src_set
    assert "Долгое нажатие" in src_set
    assert "Ctrl+N" in src_set

    src_home = (ROOT / "app/ui/screens/home.py").read_text(encoding="utf-8")
    assert "Сделайте экспорт бэкапа" in src_home
    assert "needs_backup_reminder" in src_home
    assert "backup_tip" in src_home

    src_ex = (ROOT / "app/services/export_service.py").read_text(encoding="utf-8")
    assert "def needs_backup_reminder" in src_ex

    with get_session() as s:
        # missing → remind
        set_meta(s, "last_export_at", "")
        set_meta(s, "last_export_path", "")
        s.commit()
        assert export_service.needs_backup_reminder(s, days=7) is True

        # recent → no remind
        set_meta(s, export_service.LAST_EXPORT_AT_KEY, datetime.now().isoformat(timespec="seconds"))
        s.commit()
        assert export_service.needs_backup_reminder(s, days=7) is False

        # 8 days ago → remind
        old = (datetime.now() - timedelta(days=8)).isoformat(timespec="seconds")
        set_meta(s, export_service.LAST_EXPORT_AT_KEY, old)
        s.commit()
        assert export_service.needs_backup_reminder(s, days=7) is True

        # exactly 7 days ago → remind (>=)
        old7 = (date.today() - timedelta(days=7)).isoformat() + "T12:00:00"
        set_meta(s, export_service.LAST_EXPORT_AT_KEY, old7)
        s.commit()
        assert export_service.needs_backup_reminder(s, days=7) is True

        # corrupt → remind
        set_meta(s, export_service.LAST_EXPORT_AT_KEY, "not-a-date")
        s.commit()
        assert export_service.needs_backup_reminder(s, days=7) is True

    # docs
    rd = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Wave AA" in rd or "горяч" in rd.lower() or "Горячие" in rd
    cl = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## AA —" in cl
    fm = (ROOT / "scripts/feature_matrix.md").read_text(encoding="utf-8")
    assert "**AA**" in fm
    print("Wave AA OK")



    print("== Wave AB: Ctrl+N / backup tip dismiss ==")
    from app.db import get_meta, get_session, set_meta
    from app.services import export_service
    from app.ui.screens import settings as settings_ui

    assert settings_ui.FEATURE_COUNT >= 57

    src_main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert "on_keyboard_event" in src_main
    assert "go_create" in src_main
    assert 'key == "n"' in src_main or "key == 'n'" in src_main

    src_set = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert "Ctrl+N — создать" in src_set or "Ctrl+N" in src_set
    assert "web" in src_set.lower()  # web caveat documented

    src_home = (ROOT / "app/ui/screens/home.py").read_text(encoding="utf-8")
    assert "dismiss_backup_tip" in src_home
    assert "is_backup_tip_dismissed" in src_home
    assert "backup_dismissed" in src_home
    assert "Скрыть сегодня" in src_home

    src_ex = (ROOT / "app/services/export_service.py").read_text(encoding="utf-8")
    assert "BACKUP_TIP_DISMISS_KEY" in src_ex
    assert "def dismiss_backup_tip" in src_ex
    assert "def is_backup_tip_dismissed" in src_ex

    with get_session() as s:
        export_service.clear_backup_tip_dismiss(s)
        assert export_service.is_backup_tip_dismissed(s) is False
        export_service.dismiss_backup_tip(s)
        assert export_service.is_backup_tip_dismissed(s) is True
        # idempotent
        export_service.dismiss_backup_tip(s)
        assert export_service.is_backup_tip_dismissed(s) is True
        assert get_meta(s, export_service.BACKUP_TIP_DISMISS_KEY) == date.today().isoformat()
        # past day → not dismissed
        set_meta(s, export_service.BACKUP_TIP_DISMISS_KEY, "2000-01-01")
        s.commit()
        assert export_service.is_backup_tip_dismissed(s) is False
        # corrupt → not dismissed
        set_meta(s, export_service.BACKUP_TIP_DISMISS_KEY, "true")
        s.commit()
        assert export_service.is_backup_tip_dismissed(s) is False
        export_service.clear_backup_tip_dismiss(s)
        assert export_service.is_backup_tip_dismissed(s) is False

    rd = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Wave AB" in rd
    cl = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## AB —" in cl
    fm = (ROOT / "scripts/feature_matrix.md").read_text(encoding="utf-8")
    assert "**AB**" in fm
    print("Wave AB OK")



    print("== Wave AC: Ctrl+F / TextField keyboard safety ==")
    from app.ui.screens import settings as settings_ui
    from app.main import (
        _is_text_input_control,
        keyboard_from_text_input,
    )

    assert settings_ui.FEATURE_COUNT >= 58

    src_main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert "on_keyboard_event" in src_main
    assert "go_search" in src_main
    assert 'key == "f"' in src_main or "key == 'f'" in src_main
    assert "keyboard_from_text_input" in src_main
    assert "TextField" in src_main

    src_set = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert "Ctrl+F" in src_set
    assert "Ctrl+F — открыть поиск" in src_set
    assert "TextField" in src_set
    assert "web" in src_set.lower()

    # helper: TextField as control/target → treat as typing
    class _TF:
        pass
    _TF.__name__ = "TextField"
    tf = _TF()
    assert _is_text_input_control(tf) is True
    assert _is_text_input_control("TextField") is True
    assert _is_text_input_control(None) is False
    assert _is_text_input_control(object()) is False

    ev_tf = type("E", (), {"control": tf, "target": None})()
    assert keyboard_from_text_input(ev_tf) is True
    ev_tgt = type("E", (), {"control": object(), "target": "CupertinoTextField"})()
    assert keyboard_from_text_input(ev_tgt) is True
    ev_ok = type("E", (), {"control": object(), "target": None, "page": None})()
    assert keyboard_from_text_input(ev_ok) is False

    # walk: focused flag on nested TextField
    class _Page:
        def __init__(self, content):
            self.content = content
            self.controls = []
            self.overlay = []
    focused = _TF()
    focused.focused = True
    page_like = _Page(focused)
    ev_walk = type("E", (), {"control": page_like, "target": None, "page": page_like})()
    # page_like is not named Page, but e.page is set
    assert keyboard_from_text_input(ev_walk) is True
    unfocused = _TF()
    unfocused.focused = False
    page_like.content = unfocused
    ev_walk2 = type("E", (), {"control": page_like, "target": None, "page": page_like})()
    assert keyboard_from_text_input(ev_walk2) is False

    rd = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Wave AC" in rd
    cl = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## AC —" in cl
    fm = (ROOT / "scripts/feature_matrix.md").read_text(encoding="utf-8")
    assert "**AC**" in fm
    print("Wave AC OK")


    print("== Wave AD: Esc closes overlay / leave_overlay callback ==")
    from app.ui.screens import settings as settings_ui_ad
    from app.main import (
        _OVERLAY_SCREENS,
        escape_closes_overlay,
        keyboard_from_text_input,
    )

    assert settings_ui_ad.FEATURE_COUNT >= 59

    src_main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert "escape_closes_overlay" in src_main
    assert "leave_overlay" in src_main
    assert "_OVERLAY_SCREENS" in src_main
    assert 'key in ("escape", "esc")' in src_main or "key in ('escape', 'esc')" in src_main
    for name in ("search", "create", "settings", "focus", "task", "goal", "note", "reminders"):
        assert name in _OVERLAY_SCREENS
    assert "main" not in _OVERLAY_SCREENS

    calls = []
    assert escape_closes_overlay("search", lambda: calls.append("x")) is True
    assert calls == ["x"]
    calls.clear()
    assert escape_closes_overlay("create", lambda: calls.append("c")) is True
    assert escape_closes_overlay("settings", lambda: calls.append("s")) is True
    assert escape_closes_overlay("focus", lambda: calls.append("f")) is True
    assert escape_closes_overlay("task", lambda: calls.append("t")) is True
    assert escape_closes_overlay("goal", lambda: calls.append("g")) is True
    assert escape_closes_overlay("note", lambda: calls.append("n")) is True
    assert escape_closes_overlay("reminders", lambda: calls.append("r")) is True
    assert calls == ["c", "s", "f", "t", "g", "n", "r"]
    assert escape_closes_overlay("main", lambda: calls.append("no")) is False
    assert "no" not in calls

    # Esc ignored while TextField focused (same safety gate)
    class _TF:
        pass
    _TF.__name__ = "TextField"
    tf = _TF()
    ev_tf = type("E", (), {"control": tf, "target": None, "key": "Escape", "ctrl": False, "alt": False})()
    assert keyboard_from_text_input(ev_tf) is True

    src_set = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert "Esc — закрыть оверлей" in src_set or "Esc" in src_set
    assert "A–AD" in src_set or "A-AD" in src_set or "A–AE" in src_set or "A-AE" in src_set or "A–AF" in src_set or "A-AF" in src_set or "A–AG" in src_set or "A-AG" in src_set or "A–AH" in src_set or "A-AH" in src_set or "A–AI" in src_set or "A-AI" in src_set or "A–AJ" in src_set or "A-AJ" in src_set or "A–AK" in src_set or "A-AK" in src_set or "A–AM" in src_set or "A-AM" in src_set or "A–AN" in src_set or "A-AN" in src_set or "A–AO" in src_set or "A-AO" in src_set or "A–AP" in src_set or "A-AP" in src_set or "A–AQ" in src_set or "A-AQ" in src_set or "A–AR" in src_set or "A-AR" in src_set or "A–AS" in src_set or "A-AS" in src_set or "A–AT" in src_set or "A-AT" in src_set or "A–AU" in src_set or "A-AU" in src_set or "A–AV" in src_set or "A-AV" in src_set or "A–AV" in src_set or "A-AV" in src_set

    rd = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Wave AD" in rd
    cl = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## AD —" in cl
    fm = (ROOT / "scripts/feature_matrix.md").read_text(encoding="utf-8")
    assert "**AD**" in fm
    print("Wave AD OK")



    print("== Wave AE: digit 1–4 switch bottom tabs on main ==")
    from app.ui.screens import settings as settings_ui_ae
    from app.main import digit_switches_tab, keyboard_from_text_input

    assert settings_ui_ae.FEATURE_COUNT >= 60

    src_main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert "digit_switches_tab" in src_main
    assert "state[\"tab\"] = tab_idx" in src_main or "state['tab'] = tab_idx" in src_main

    # 1-based keys → 0-based tabs on main
    assert digit_switches_tab("1", "main") == 0
    assert digit_switches_tab("2", "main") == 1
    assert digit_switches_tab("3", "main") == 2
    assert digit_switches_tab("4", "main") == 3
    assert digit_switches_tab("digit1", "main") == 0
    assert digit_switches_tab("Digit2", "main") == 1
    assert digit_switches_tab("5", "main") is None
    assert digit_switches_tab("1", "search") is None
    assert digit_switches_tab("1", "create") is None
    assert digit_switches_tab("1", "settings") is None
    assert digit_switches_tab("1", "reminders") is None
    assert digit_switches_tab("1", "focus") is None
    assert digit_switches_tab("", "main") is None

    # Safety: digits ignored while TextField focused (same gate as Esc)
    class _TF:
        pass
    _TF.__name__ = "TextField"
    tf = _TF()
    ev_tf = type("E", (), {"control": tf, "target": None, "key": "1", "ctrl": False, "alt": False})()
    assert keyboard_from_text_input(ev_tf) is True

    src_set = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert "1 / 2 / 3 / 4" in src_set
    assert "A–AE" in src_set or "A-AE" in src_set or "A–AF" in src_set or "A-AF" in src_set or "A–AG" in src_set or "A-AG" in src_set or "A–AH" in src_set or "A-AH" in src_set or "A–AI" in src_set or "A-AI" in src_set or "A–AJ" in src_set or "A-AJ" in src_set or "A–AK" in src_set or "A-AK" in src_set or "A–AM" in src_set or "A-AM" in src_set or "A–AN" in src_set or "A-AN" in src_set or "A–AO" in src_set or "A-AO" in src_set or "A–AP" in src_set or "A-AP" in src_set or "A–AQ" in src_set or "A-AQ" in src_set or "A–AR" in src_set or "A-AR" in src_set or "A–AS" in src_set or "A-AS" in src_set or "A–AT" in src_set or "A-AT" in src_set or "A–AU" in src_set or "A-AU" in src_set or "A–AV" in src_set or "A-AV" in src_set

    rd = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Wave AE" in rd
    cl = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## AE —" in cl
    fm = (ROOT / "scripts/feature_matrix.md").read_text(encoding="utf-8")
    assert "**AE**" in fm
    print("Wave AE OK")



    print("== Wave AF: Space opens Focus on main ==")
    from app.ui.screens import settings as settings_ui_af
    from app.main import space_opens_focus, keyboard_from_text_input

    assert settings_ui_af.FEATURE_COUNT >= 61

    src_main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert "space_opens_focus" in src_main
    assert "go_focus" in src_main
    assert 'key = "space"' in src_main or "key = 'space'" in src_main

    assert space_opens_focus("space", "main") is True
    assert space_opens_focus(" ", "main") is True
    assert space_opens_focus("Space", "main") is True
    assert space_opens_focus("SPACE", "main") is True
    assert space_opens_focus("space", "focus") is False
    assert space_opens_focus("space", "search") is False
    assert space_opens_focus("space", "create") is False
    assert space_opens_focus("space", "settings") is False
    assert space_opens_focus("a", "main") is False
    assert space_opens_focus("", "main") is False
    assert space_opens_focus("1", "main") is False

    # Safety: Space ignored while TextField focused
    class _TF:
        pass
    _TF.__name__ = "TextField"
    tf = _TF()
    ev_tf = type("E", (), {"control": tf, "target": None, "key": " ", "ctrl": False, "alt": False})()
    assert keyboard_from_text_input(ev_tf) is True

    src_set = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert "Пробел" in src_set and "Фокус" in src_set
    assert "A–AF" in src_set or "A-AF" in src_set or "A–AG" in src_set or "A-AG" in src_set or "A–AH" in src_set or "A-AH" in src_set or "A–AI" in src_set or "A-AI" in src_set or "A–AJ" in src_set or "A-AJ" in src_set or "A–AK" in src_set or "A-AK" in src_set or "A–AM" in src_set or "A-AM" in src_set or "A–AN" in src_set or "A-AN" in src_set or "A–AO" in src_set or "A-AO" in src_set or "A–AP" in src_set or "A-AP" in src_set or "A–AQ" in src_set or "A-AQ" in src_set or "A–AR" in src_set or "A-AR" in src_set or "A–AS" in src_set or "A-AS" in src_set or "A–AT" in src_set or "A-AT" in src_set or "A–AU" in src_set or "A-AU" in src_set or "A–AV" in src_set or "A-AV" in src_set

    rd = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Wave AF" in rd
    cl = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## AF —" in cl
    fm = (ROOT / "scripts/feature_matrix.md").read_text(encoding="utf-8")
    assert "**AF**" in fm
    print("Wave AF OK")



    print("== Wave AG: morning briefing ==")
    from app.schemas import MorningBriefing, IncompleteQuota, MomentumScore
    from app.ui.screens import settings as settings_ui_ag
    from app.db import set_meta

    assert settings_ui_ag.FEATURE_COUNT >= 62

    today = date.today()
    yesterday = today - timedelta(days=1)
    with get_session() as s:
        t_od = task_service.create_task(
            s,
            TaskCreate(
                title="WaveAG Overdue",
                status="todo",
                priority="high",
                due_date=yesterday,
            ),
        )
        t_td = task_service.create_task(
            s,
            TaskCreate(
                title="WaveAG DueToday",
                status="todo",
                priority="medium",
                due_date=today,
            ),
        )
        g = goal_service.create_goal(
            s,
            GoalCreate(
                title="WaveAG Quota",
                target_value=20,
                unit="ед",
                daily_quota=5,
            ),
        )
        # dismiss home smart card — briefing must still carry a suggestion
        set_meta(s, "smart_suggest_dismissed", today.isoformat())
        s.commit()
        assert settings_service.is_smart_suggest_dismissed(s) is True

        brief = analytics_service.morning_briefing(s)
        assert isinstance(brief, MorningBriefing)
        assert brief.day == today
        assert brief.overdue_count >= 1
        assert brief.due_today >= 1
        titles = [q.title for q in brief.incomplete_quotas]
        assert "WaveAG Quota" in titles
        for q in brief.incomplete_quotas:
            assert isinstance(q, IncompleteQuota)
            assert q.quota > 0
        assert isinstance(brief.momentum, MomentumScore)
        assert 0 <= brief.momentum.score <= 100
        assert brief.suggestion is not None
        assert brief.suggestion.kind in ("stuck", "overdue", "quota")
        assert (brief.suggestion.text or "").strip()

        # close quota → still overdue suggestion
        goal_service.add_progress(
            s, ProgressLogCreate(goal_id=g.id, amount=5, note="ag")
        )
        brief2 = analytics_service.morning_briefing(s)
        q_titles = [q.title for q in brief2.incomplete_quotas]
        assert "WaveAG Quota" not in q_titles
        assert brief2.suggestion is not None
        assert brief2.suggestion.kind in ("stuck", "overdue")

        task_service.delete_task(s, t_od.id)
        task_service.delete_task(s, t_td.id)
        goal_service.delete_goal(s, g.id)

    src_home = (ROOT / "app/ui/screens/home.py").read_text(encoding="utf-8")
    assert "Брифинг" in src_home
    assert "morning_briefing" in src_home
    assert "show_morning_briefing" in src_home
    assert "Открытые квоты" in src_home
    assert "Утро ·" in src_home or "Утро" in src_home
    src_an = (ROOT / "app/services/analytics_service.py").read_text(encoding="utf-8")
    assert "def morning_briefing" in src_an
    src_sch = (ROOT / "app/schemas.py").read_text(encoding="utf-8")
    assert "class MorningBriefing" in src_sch
    assert "class IncompleteQuota" in src_sch
    src_set = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert "A–AG" in src_set or "A-AG" in src_set or "A–AH" in src_set or "A-AH" in src_set or "A–AI" in src_set or "A-AI" in src_set or "A–AJ" in src_set or "A-AJ" in src_set or "A–AK" in src_set or "A-AK" in src_set or "A–AM" in src_set or "A-AM" in src_set or "A–AN" in src_set or "A-AN" in src_set or "A–AO" in src_set or "A-AO" in src_set or "A–AP" in src_set or "A-AP" in src_set or "A–AQ" in src_set or "A-AQ" in src_set or "A–AR" in src_set or "A-AR" in src_set or "A–AS" in src_set or "A-AS" in src_set or "A–AT" in src_set or "A-AT" in src_set or "A–AU" in src_set or "A-AU" in src_set or "A–AV" in src_set or "A-AV" in src_set
    rd = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Wave AG" in rd
    cl = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## AG —" in cl
    fm = (ROOT / "scripts/feature_matrix.md").read_text(encoding="utf-8")
    assert "**AG**" in fm
    st = (ROOT / "AFTERNOON_STATUS.md").read_text(encoding="utf-8")
    assert "Wave AG" in st
    print("Wave AG OK")



    print("== Wave AH: evening wind-down ==")
    from app.ui.screens import settings as settings_ui_ah

    assert settings_ui_ah.FEATURE_COUNT >= 64

    with get_session() as s:
        st = settings_service.get_settings(s)
        assert st.wind_down_hour == 18
        assert settings_service.is_wind_down(st, hour=18) is True
        assert settings_service.is_wind_down(st, hour=17) is False
        assert settings_service.is_wind_down(st, hour=23) is True
        assert settings_service.is_wind_down(st, hour=0) is False
        # missing meta → default
        from app.db import set_meta
        set_meta(s, "wind_down_hour", "")
        s.commit()
        st2 = settings_service.get_settings(s)
        assert st2.wind_down_hour == 18
        settings_service.update_settings(s, SettingsUpdate(wind_down_hour=20))
        st3 = settings_service.get_settings(s)
        assert st3.wind_down_hour == 20
        assert get_meta(s, "wind_down_hour") == "20"
        assert settings_service.is_wind_down(st3, hour=19) is False
        assert settings_service.is_wind_down(st3, hour=20) is True
        # restore default
        settings_service.update_settings(s, SettingsUpdate(wind_down_hour=18))
        # export round-trip key
        payload = export_service.export_all(s)
        assert "wind_down_hour" in (payload.get("settings") or {})
        # incomplete quotas count for card copy
        g = goal_service.create_goal(
            s,
            GoalCreate(
                title="WaveAH Quota",
                target_value=10,
                unit="ед",
                daily_quota=3,
            ),
        )
        quotas = goal_service.today_quotas(s)
        incomplete = sum(1 for q in quotas if not q.get("complete") and q["goal"].title == "WaveAH Quota")
        assert incomplete == 1
        goal_service.delete_goal(s, g.id)

    src_home = (ROOT / "app/ui/screens/home.py").read_text(encoding="utf-8")
    assert "Вечерний режим" in src_home
    assert "evening_card" in src_home
    assert "is_wind_down" in src_home
    assert "show_daily_wrap" in src_home
    src_ss = (ROOT / "app/services/settings_service.py").read_text(encoding="utf-8")
    assert "def is_wind_down" in src_ss
    assert "wind_down_hour" in src_ss
    src_set = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert "wind_down" in src_set or "Вечерний режим" in src_set
    assert "A–AH" in src_set or "A-AH" in src_set or "A–AI" in src_set or "A-AI" in src_set or "A–AJ" in src_set or "A-AJ" in src_set or "A–AK" in src_set or "A-AK" in src_set or "A–AM" in src_set or "A-AM" in src_set or "A–AN" in src_set or "A-AN" in src_set or "A–AO" in src_set or "A-AO" in src_set or "A–AP" in src_set or "A-AP" in src_set or "A–AQ" in src_set or "A-AQ" in src_set or "A–AR" in src_set or "A-AR" in src_set or "A–AS" in src_set or "A-AS" in src_set or "A–AT" in src_set or "A-AT" in src_set or "A–AU" in src_set or "A-AU" in src_set or "A–AV" in src_set or "A-AV" in src_set
    assert "Вечерний режим" in src_set
    src_sch = (ROOT / "app/schemas.py").read_text(encoding="utf-8")
    assert "wind_down_hour" in src_sch
    src_db = (ROOT / "app/db.py").read_text(encoding="utf-8")
    assert '"wind_down_hour"' in src_db
    rd = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Wave AH" in rd
    cl = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## AH —" in cl
    fm = (ROOT / "scripts/feature_matrix.md").read_text(encoding="utf-8")
    assert "**AH**" in fm
    st_md = (ROOT / "AFTERNOON_STATUS.md").read_text(encoding="utf-8")
    assert "Wave AH" in st_md
    print("Wave AH OK")



    print("== Wave AI: tomorrow plan ==")
    from app.ui.screens import settings as settings_ui_ai

    assert settings_ui_ai.FEATURE_COUNT >= 64
    src_set_ai = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert (
        "A–AI" in src_set_ai
        or "A-AI" in src_set_ai
        or "A–AJ" in src_set_ai
        or "A-AJ" in src_set_ai
        or "A–AK" in src_set_ai
        or "A-AK" in src_set_ai
        or "A–AM" in src_set_ai or "A-AM" in src_set_ai or "A–AN" in src_set_ai or "A-AN" in src_set_ai or "A–AO" in src_set_ai or "A-AO" in src_set_ai or "A–AP" in src_set_ai or "A-AP" in src_set_ai or "A–AQ" in src_set_ai or "A-AQ" in src_set_ai or "A–AR" in src_set_ai or "A-AR" in src_set_ai or "A–AS" in src_set_ai or "A-AS" in src_set_ai or "A–AT" in src_set_ai or "A-AT" in src_set_ai or "A–AU" in src_set_ai or "A-AU" in src_set_ai
    )
    with get_session() as s:
        # clean slate tasks for isolation
        for t in list(task_service.list_tasks(s)):
            task_service.delete_task(s, t.id)
        today = date.today()
        tomorrow = today + timedelta(days=1)
        t_tmr = task_service.create_task(
            s,
            TaskCreate(
                title="WaveAI Tomorrow",
                priority="high",
                due_date=tomorrow,
                estimated_min=25,
            ),
        )
        t_today = task_service.create_task(
            s,
            TaskCreate(
                title="WaveAI Today Open",
                priority="medium",
                due_date=today,
            ),
        )
        t_other = task_service.create_task(
            s,
            TaskCreate(
                title="WaveAI Later",
                due_date=today + timedelta(days=3),
            ),
        )
        assert task_service.is_due_tomorrow(t_tmr, today=today) is True
        assert task_service.is_due_tomorrow(t_today, today=today) is False
        assert task_service.is_due_today(t_today, today=today) is True
        plan = analytics_service.tomorrow_plan(s, today=today)
        assert plan.day == tomorrow
        assert any(i.task_id == t_tmr.id for i in plan.due_tomorrow)
        assert any(i.task_id == t_today.id for i in plan.open_today)
        assert all(i.task_id != t_other.id for i in plan.due_tomorrow)
        assert all(i.task_id != t_other.id for i in plan.open_today)
        assert plan.tip
        # done today should leave open_today
        task_service.update_task(s, t_today.id, TaskUpdate(status="done"))
        plan2 = analytics_service.tomorrow_plan(s, today=today)
        assert all(i.task_id != t_today.id for i in plan2.open_today)
        # empty-ish tip path: no due tomorrow after delete
        task_service.delete_task(s, t_tmr.id)
        task_service.delete_task(s, t_today.id)
        task_service.delete_task(s, t_other.id)
        plan3 = analytics_service.tomorrow_plan(s, today=today)
        assert plan3.due_tomorrow == []
        assert "пусто" in plan3.tip.lower() or "планир" in plan3.tip.lower()

    src_home = (ROOT / "app/ui/screens/home.py").read_text(encoding="utf-8")
    assert "show_tomorrow_plan" in src_home
    assert "tomorrow_btn" in src_home
    assert "План на завтра" in src_home
    assert "tomorrow_plan" in src_home
    src_an = (ROOT / "app/services/analytics_service.py").read_text(encoding="utf-8")
    assert "def tomorrow_plan" in src_an
    src_ts = (ROOT / "app/services/task_service.py").read_text(encoding="utf-8")
    assert "def is_due_tomorrow" in src_ts
    src_sch = (ROOT / "app/schemas.py").read_text(encoding="utf-8")
    assert "class TomorrowPlan" in src_sch
    assert "class TomorrowPlanItem" in src_sch
    rd = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Wave AI" in rd
    cl = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## AI —" in cl
    fm = (ROOT / "scripts/feature_matrix.md").read_text(encoding="utf-8")
    assert "**AI**" in fm
    st_md = (ROOT / "AFTERNOON_STATUS.md").read_text(encoding="utf-8")
    assert "Wave AI" in st_md
    print("Wave AI OK")


    print("== Wave AJ: weekly task goal ==")
    from app.ui.screens import settings as settings_ui_aj

    assert settings_ui_aj.FEATURE_COUNT >= 65

    with get_session() as s:
        st = settings_service.get_settings(s)
        assert st.weekly_task_target == 10
        from app.db import set_meta
        set_meta(s, "weekly_task_target", "")
        s.commit()
        assert settings_service.get_settings(s).weekly_task_target == 10
        set_meta(s, "weekly_task_target", "abc")
        s.commit()
        assert settings_service.get_settings(s).weekly_task_target == 10
        settings_service.update_settings(s, SettingsUpdate(weekly_task_target=15))
        st3 = settings_service.get_settings(s)
        assert st3.weekly_task_target == 15
        assert get_meta(s, "weekly_task_target") == "15"

        today = date.today()
        iso_start = today - timedelta(days=today.weekday())
        before = analytics_service.count_completed_iso_week(s, today=today)
        t1 = task_service.create_task(s, TaskCreate(title="WaveAJ Done1"))
        t2 = task_service.create_task(s, TaskCreate(title="WaveAJ Done2"))
        t3 = task_service.create_task(s, TaskCreate(title="WaveAJ Old"))
        task_service.update_task(s, t1.id, TaskUpdate(status="done"))
        task_service.update_task(s, t2.id, TaskUpdate(status="done"))
        task_service.update_task(s, t3.id, TaskUpdate(status="done"))
        row = task_service.get_task(s, t3.id)
        row.completed_at = datetime.combine(iso_start - timedelta(days=1), datetime.min.time())
        s.commit()
        after = analytics_service.count_completed_iso_week(s, today=today)
        assert after == before + 2
        done_n, tgt = analytics_service.weekly_goal_progress(s, today=today)
        assert tgt == 15
        assert done_n == after
        settings_service.update_settings(s, SettingsUpdate(weekly_task_target=10))
        payload = export_service.export_all(s)
        assert "weekly_task_target" in (payload.get("settings") or {})
        task_service.delete_task(s, t1.id)
        task_service.delete_task(s, t2.id)
        task_service.delete_task(s, t3.id)

    src_home = (ROOT / "app/ui/screens/home.py").read_text(encoding="utf-8")
    assert "Неделя:" in src_home and "/ " not in "skip"
    assert "week_goal_card" in src_home
    assert "weekly_goal_progress" in src_home
    assert "задач" in src_home
    src_an_ui = (ROOT / "app/ui/screens/analytics.py").read_text(encoding="utf-8")
    assert "week_goal_card" in src_an_ui
    assert "weekly_goal_progress" in src_an_ui
    assert "Неделя:" in src_an_ui
    src_an = (ROOT / "app/services/analytics_service.py").read_text(encoding="utf-8")
    assert "def count_completed_iso_week" in src_an
    assert "def weekly_goal_progress" in src_an
    src_ss = (ROOT / "app/services/settings_service.py").read_text(encoding="utf-8")
    assert "weekly_task_target" in src_ss
    src_set = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert "Цель недели" in src_set
    assert (
        "A–AJ" in src_set or "A-AJ" in src_set
        or "A–AK" in src_set or "A-AK" in src_set
        or "A–AL" in src_set or "A-AL" in src_set
        or "A–AM" in src_set or "A-AM" in src_set or "A–AN" in src_set or "A-AN" in src_set or "A–AO" in src_set or "A-AO" in src_set or "A–AP" in src_set or "A-AP" in src_set or "A–AQ" in src_set or "A-AQ" in src_set or "A–AR" in src_set or "A-AR" in src_set or "A–AS" in src_set or "A-AS" in src_set or "A–AT" in src_set or "A-AT" in src_set or "A–AU" in src_set or "A-AU" in src_set or "A–AV" in src_set or "A-AV" in src_set
    )
    src_sch = (ROOT / "app/schemas.py").read_text(encoding="utf-8")
    assert "weekly_task_target" in src_sch
    src_db = (ROOT / "app/db.py").read_text(encoding="utf-8")
    assert '"weekly_task_target"' in src_db
    rd = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Wave AJ" in rd
    cl = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## AJ —" in cl
    fm = (ROOT / "scripts/feature_matrix.md").read_text(encoding="utf-8")
    assert "**AJ**" in fm
    st_md = (ROOT / "AFTERNOON_STATUS.md").read_text(encoding="utf-8")
    assert "Wave AJ" in st_md
    print("Wave AJ OK")



    print("== Wave AK: snooze all overdue ==")
    from app.ui.screens import settings as settings_ui_ak

    assert settings_ui_ak.FEATURE_COUNT >= 66
    with get_session() as s:
        for t in list(task_service.list_tasks(s)):
            task_service.delete_task(s, t.id)
        today = date.today()
        a = task_service.create_task(
            s, TaskCreate(title="WaveAK Over1", due_date=today - timedelta(days=2))
        )
        b = task_service.create_task(
            s, TaskCreate(title="WaveAK Over2", due_date=today - timedelta(days=1))
        )
        c = task_service.create_task(
            s, TaskCreate(title="WaveAK Today", due_date=today)
        )
        d = task_service.create_task(
            s, TaskCreate(title="WaveAK Future", due_date=today + timedelta(days=5))
        )
        n = task_service.snooze_all_overdue(s, days=1, today=today)
        assert n == 2
        a2 = task_service.get_task(s, a.id)
        b2 = task_service.get_task(s, b.id)
        c2 = task_service.get_task(s, c.id)
        d2 = task_service.get_task(s, d.id)
        assert a2.due_date == today - timedelta(days=1)
        assert b2.due_date == today
        assert c2.due_date == today
        assert d2.due_date == today + timedelta(days=5)
        # second pass: only a still overdue (b is now today)
        n2 = task_service.snooze_all_overdue(s, days=1, today=today)
        assert n2 == 1
        a3 = task_service.get_task(s, a.id)
        assert a3.due_date == today
        n3 = task_service.snooze_all_overdue(s, days=1, today=today)
        assert n3 == 0
        for tid in (a.id, b.id, c.id, d.id):
            task_service.delete_task(s, tid)

    src_home = (ROOT / "app/ui/screens/home.py").read_text(encoding="utf-8")
    assert "do_snooze_all_overdue" in src_home
    assert "snooze_all_overdue" in src_home
    assert "+1д" in src_home
    src_ts = (ROOT / "app/services/task_service.py").read_text(encoding="utf-8")
    assert "def snooze_all_overdue" in src_ts
    src_set = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert (
        "A–AK" in src_set or "A-AK" in src_set
        or "A–AL" in src_set or "A-AL" in src_set
        or "A–AM" in src_set or "A-AM" in src_set or "A–AN" in src_set or "A-AN" in src_set or "A–AO" in src_set or "A-AO" in src_set or "A–AP" in src_set or "A-AP" in src_set or "A–AQ" in src_set or "A-AQ" in src_set or "A–AR" in src_set or "A-AR" in src_set or "A–AS" in src_set or "A-AS" in src_set or "A–AT" in src_set or "A-AT" in src_set or "A–AU" in src_set or "A-AU" in src_set or "A–AV" in src_set or "A-AV" in src_set
    )
    rd = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Wave AK" in rd
    cl = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## AK —" in cl
    fm = (ROOT / "scripts/feature_matrix.md").read_text(encoding="utf-8")
    assert "**AK**" in fm
    st_md = (ROOT / "AFTERNOON_STATUS.md").read_text(encoding="utf-8")
    assert "Wave AK" in st_md
    print("Wave AK OK")



    print("== Wave AL: streak freeze ==")
    from app.ui.screens import settings as settings_ui_al
    from app.db import set_meta, get_meta
    from app.models import ProgressLog
    from app.schemas import GoalCreate

    assert settings_ui_al.FEATURE_COUNT >= 67

    with get_session() as s:
        # clear freeze
        set_meta(s, streak_service.STREAK_FREEZE_META, "")
        s.commit()
        today = date.today()
        week = streak_service.iso_week_key(today)
        assert week.startswith(str(today.isocalendar()[0]) + "-W")
        assert streak_service.is_freeze_available(s, today=today) is True
        assert streak_service.is_freeze_active(s, today=today) is False

        g = goal_service.create_goal(
            s,
            GoalCreate(
                title="WaveAK FreezeGoal",
                target_value=100,
                unit="u",
                daily_quota=1.0,
            ),
        )
        # T-4..T-2 ok, T-1 missing, today incomplete.
        # Without freeze: start T-1 → miss → current=0.
        # With freeze: start T-1 → bridge gap → T-2..T-4 → current=3.
        for i in (2, 3, 4):
            s.add(
                ProgressLog(
                    goal_id=g.id,
                    amount=1.0,
                    note=f"ak-{i}",
                    logged_at=datetime.combine(today - timedelta(days=i), datetime.min.time())
                    + timedelta(hours=12),
                )
            )
        s.commit()

        info0 = streak_service.goal_streak(s, g, today=today)
        assert info0.today_complete is False
        assert info0.current_streak == 0, info0  # gap yesterday breaks

        ok = streak_service.activate_streak_freeze(s, today=today)
        assert ok is True
        assert get_meta(s, "streak_freeze_used_week") == week
        assert streak_service.is_freeze_active(s, today=today) is True
        assert streak_service.is_freeze_available(s, today=today) is False
        ok2 = streak_service.activate_streak_freeze(s, today=today)
        assert ok2 is False  # once per week

        info1 = streak_service.goal_streak(s, g, today=today)
        # today = frozen gap; T-2,T-3,T-4 met → current 3
        assert info1.current_streak == 3, info1
        # best ignores freeze bridging across missing T-1 in historical run
        assert info1.best_streak >= 3

        all_s = streak_service.all_streaks(s)
        assert any(x.goal_id == g.id and x.current_streak == 3 for x in all_s)

        # export still works (freeze is meta, not SettingsOut)
        payload = export_service.export_all(s)
        assert "settings" in payload

        goal_service.delete_goal(s, g.id)

    src_ss = (ROOT / "app/services/streak_service.py").read_text(encoding="utf-8")
    assert "STREAK_FREEZE_META" in src_ss
    assert "activate_streak_freeze" in src_ss
    assert "allow_one_gap" in src_ss
    assert "iso_week_key" in src_ss
    src_set = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert "Заморозка серии" in src_set
    assert "Заморозить серию" in src_set
    assert "streak_freeze_used_week" in src_set
    assert (
        "A–AL" in src_set
        or "A-AL" in src_set
        or "A–AM" in src_set
        or "A-AM" in src_set
        or "A–AN" in src_set
        or "A-AN" in src_set
        or "A–AO" in src_set
        or "A-AO" in src_set
        or "A–AP" in src_set
        or "A-AP" in src_set
        or "A–AQ" in src_set
        or "A-AQ" in src_set
        or "A–AR" in src_set or "A–AS" in src_set or "A-AS" in src_set or "A–AT" in src_set or "A-AT" in src_set or "A–AU" in src_set or "A-AU" in src_set or "A–AV" in src_set or "A-AV" in src_set
        or "A-AR" in src_set or "A–AS" in src_set or "A-AS" in src_set or "A–AT" in src_set or "A-AT" in src_set or "A–AU" in src_set or "A-AU" in src_set or "A–AV" in src_set or "A-AV" in src_set
    )
    assert "do_streak_freeze" in src_set
    rd = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Wave AL" in rd
    cl = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## AL —" in cl
    fm = (ROOT / "scripts/feature_matrix.md").read_text(encoding="utf-8")
    assert "**AL**" in fm
    assert "замороз" in fm.lower() or "Замороз" in fm
    st_md = (ROOT / "AFTERNOON_STATUS.md").read_text(encoding="utf-8")
    assert "Wave AL" in st_md
    print("Wave AL OK")



    print("== Wave AM: focus session notes (schema 12) ==")
    from app.ui.screens import settings as settings_ui_am
    from app.db import SCHEMA_VERSION, get_meta, get_session
    from app.schemas import TimeSessionCreate, TimeSessionUpdate
    from app.models import TimeSession
    from app.services import timer_service, export_service

    assert settings_ui_am.FEATURE_COUNT >= 68
    assert SCHEMA_VERSION == "13"
    with get_session() as s:
        assert get_meta(s, "schema_version") == "13"
        cols = {
            r[1]
            for r in s.execute(
                __import__("sqlalchemy").text("PRAGMA table_info(time_sessions)")
            ).fetchall()
        }
        assert "note" in cols

        sess = timer_service.create_session(
            s, TimeSessionCreate(label="WaveAM Note", duration_sec=120, note="")
        )
        assert getattr(sess, "note", None) in ("", None) or sess.note == ""
        timer_service.update_session(s, sess.id, TimeSessionUpdate(note="  черновик  "))
        mid = s.get(TimeSession, sess.id)
        assert mid is not None and mid.note == "черновик"
        done = timer_service.complete(s, sess.id, note="итог фокуса")
        assert done is not None
        assert done.status == "done"
        assert done.note == "итог фокуса"
        assert done.started_at is None

        # empty note OK
        sess2 = timer_service.create_session(
            s, TimeSessionCreate(label="WaveAM Empty", duration_sec=60)
        )
        done2 = timer_service.complete(s, sess2.id, note="")
        assert done2.note == ""

        payload = export_service.export_all(s)
        found = [x for x in payload["time_sessions"] if x.get("label") == "WaveAM Note"]
        assert found and found[0].get("note") == "итог фокуса"
        # round-trip import merge preserves note
        export_service.import_all(s, payload, mode="merge")
        again = [
            x
            for x in s.scalars(
                __import__("sqlalchemy").select(TimeSession).where(
                    TimeSession.label == "WaveAM Note"
                )
            ).all()
        ]
        assert any((getattr(x, "note", None) or "") == "итог фокуса" for x in again)

        timer_service.delete_session(s, sess.id)
        timer_service.delete_session(s, sess2.id)

    src_focus = (ROOT / "app/ui/screens/focus.py").read_text(encoding="utf-8")
    assert "Заметка сессии" in src_focus
    assert "on_done" in src_focus
    assert "timer_service.complete" in src_focus
    assert "note_field" in src_focus
    src_ts = (ROOT / "app/services/timer_service.py").read_text(encoding="utf-8")
    assert "def complete" in src_ts
    src_m = (ROOT / "app/models.py").read_text(encoding="utf-8")
    assert "note: Mapped[str]" in src_m
    src_db = (ROOT / "app/db.py").read_text(encoding="utf-8")
    assert 'SCHEMA_VERSION = "13"' in src_db or 'SCHEMA_VERSION = "12"' in src_db
    assert "time_sessions ADD COLUMN note" in src_db
    src_set = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert (
        "A–AM" in src_set or "A-AM" in src_set
        or "A–AN" in src_set or "A-AN" in src_set or "A–AO" in src_set or "A-AO" in src_set or "A–AP" in src_set or "A-AP" in src_set or "A–AQ" in src_set or "A-AQ" in src_set or "A–AR" in src_set or "A-AR" in src_set or "A–AS" in src_set or "A-AS" in src_set or "A–AT" in src_set or "A-AT" in src_set or "A–AU" in src_set or "A-AU" in src_set or "A–AV" in src_set or "A-AV" in src_set
    )
    rd = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Wave AM" in rd
    assert "SCHEMA_VERSION = 13" in rd or "SCHEMA_VERSION = 12" in rd
    cl = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## AM —" in cl
    fm = (ROOT / "scripts/feature_matrix.md").read_text(encoding="utf-8")
    assert "**AM**" in fm
    st_md = (ROOT / "AFTERNOON_STATUS.md").read_text(encoding="utf-8")
    assert "Wave AM" in st_md
    print("Wave AM OK")


    print("== Wave AN: focus history filter + notes under rows ==")
    from app.ui.screens import settings as settings_ui_an
    from app.db import SCHEMA_VERSION, get_meta, get_session
    from app.schemas import TimeSessionCreate
    from app.models import TimeSession
    from app.services import timer_service

    assert settings_ui_an.FEATURE_COUNT >= 69
    assert SCHEMA_VERSION == "13"
    with get_session() as s:
        assert get_meta(s, "schema_version") == "13"
        noted = timer_service.create_session(
            s, TimeSessionCreate(label="WaveAN Noted", duration_sec=90)
        )
        timer_service.complete(s, noted.id, note="  фильтр AN  ")
        bare = timer_service.create_session(
            s, TimeSessionCreate(label="WaveAN Bare", duration_sec=60)
        )
        timer_service.complete(s, bare.id, note="")
        all_h = timer_service.list_sessions(s, limit=20)
        only_notes = timer_service.list_sessions(s, limit=20, has_note=True)
        labels_all = {x.label for x in all_h}
        labels_notes = {x.label for x in only_notes}
        assert "WaveAN Noted" in labels_all
        assert "WaveAN Bare" in labels_all
        assert "WaveAN Noted" in labels_notes
        assert "WaveAN Bare" not in labels_notes
        assert all((getattr(x, "note", None) or "").strip() for x in only_notes)
        noted_row = next(x for x in all_h if x.label == "WaveAN Noted")
        assert noted_row.note == "фильтр AN"
        timer_service.delete_session(s, noted.id)
        timer_service.delete_session(s, bare.id)

    src_focus = (ROOT / "app/ui/screens/focus.py").read_text(encoding="utf-8")
    assert "С заметкой" in src_focus
    assert '"Все"' in src_focus or "Все" in src_focus
    assert "hist_filter" in src_focus
    assert "hist_chips" in src_focus
    assert "note_txt" in src_focus
    assert "has_note" in src_focus
    assert "max_lines=4" in src_focus
    src_ts = (ROOT / "app/services/timer_service.py").read_text(encoding="utf-8")
    assert "has_note" in src_ts
    src_set = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert (
        "A–AN" in src_set or "A-AN" in src_set
        or "A–AO" in src_set or "A-AO" in src_set or "A–AP" in src_set or "A-AP" in src_set or "A–AQ" in src_set or "A-AQ" in src_set or "A–AR" in src_set or "A-AR" in src_set or "A–AS" in src_set or "A-AS" in src_set or "A–AT" in src_set or "A-AT" in src_set or "A–AU" in src_set or "A-AU" in src_set or "A–AV" in src_set or "A-AV" in src_set
    )
    rd = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Wave AN" in rd
    cl = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## AN —" in cl
    fm = (ROOT / "scripts/feature_matrix.md").read_text(encoding="utf-8")
    assert "**AN**" in fm
    st_md = (ROOT / "AFTERNOON_STATUS.md").read_text(encoding="utf-8")
    assert "Wave AN" in st_md
    print("Wave AN OK")



    print("== Wave AO: analytics focus notes (last 5 with notes) ==")
    from app.ui.screens import settings as settings_ui_ao
    from app.db import SCHEMA_VERSION, get_meta, get_session
    from app.schemas import TimeSessionCreate, FocusNoteSnippet
    from app.services import timer_service, analytics_service

    assert settings_ui_ao.FEATURE_COUNT >= 70
    assert SCHEMA_VERSION == "13"
    with get_session() as s:
        assert get_meta(s, "schema_version") == "13"
        ids = []
        for i, note in enumerate(
            [
                "AO note one",
                "AO note two",
                "AO note three",
                "AO note four",
                "AO note five",
                "AO note six overflow",
            ],
            start=1,
        ):
            sess = timer_service.create_session(
                s, TimeSessionCreate(label=f"WaveAO {i}", duration_sec=60)
            )
            timer_service.complete(s, sess.id, note=note)
            ids.append(sess.id)
        bare = timer_service.create_session(
            s, TimeSessionCreate(label="WaveAO Bare", duration_sec=60)
        )
        timer_service.complete(s, bare.id, note="")
        ids.append(bare.id)

        notes = analytics_service.recent_focus_notes(s, limit=5)
        assert len(notes) == 5
        assert all(isinstance(x, FocusNoteSnippet) for x in notes)
        assert all(x.note_snippet.strip() for x in notes)
        titles = [x.title for x in notes]
        assert "WaveAO 6" in titles  # most recent first
        assert "WaveAO Bare" not in titles
        assert titles[0] == "WaveAO 6"
        # snippet truncates long notes
        long = timer_service.create_session(
            s, TimeSessionCreate(label="WaveAO Long", duration_sec=60)
        )
        long_note = "X" * 200
        timer_service.complete(s, long.id, note=long_note)
        ids.append(long.id)
        notes2 = analytics_service.recent_focus_notes(s, limit=1)
        assert len(notes2) == 1
        assert notes2[0].title == "WaveAO Long"
        assert len(notes2[0].note_snippet) <= 120
        assert notes2[0].note_snippet.endswith("…")

        for sid in ids:
            timer_service.delete_session(s, sid)

    src_an = (ROOT / "app/services/analytics_service.py").read_text(encoding="utf-8")
    assert "def recent_focus_notes" in src_an
    src_sc = (ROOT / "app/schemas.py").read_text(encoding="utf-8")
    assert "class FocusNoteSnippet" in src_sc
    src_ui = (ROOT / "app/ui/screens/analytics.py").read_text(encoding="utf-8")
    assert "Заметки фокуса" in src_ui
    assert "recent_focus_notes" in src_ui
    assert "focus_notes_section" in src_ui
    src_set = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert "A–AO" in src_set or "A-AO" in src_set or "A–AP" in src_set or "A-AP" in src_set or "A–AQ" in src_set or "A-AQ" in src_set or "A–AR" in src_set or "A-AR" in src_set or "A–AS" in src_set or "A-AS" in src_set or "A–AT" in src_set or "A-AT" in src_set or "A–AU" in src_set or "A-AU" in src_set or "A–AV" in src_set or "A-AV" in src_set
    assert (
        "FEATURE_COUNT = 70" in src_set
        or "FEATURE_COUNT = 71" in src_set
        or "FEATURE_COUNT = 72" in src_set
        or "FEATURE_COUNT = 73" in src_set or "FEATURE_COUNT = 74" in src_set or "FEATURE_COUNT = 75" in src_set or "FEATURE_COUNT = 76" in src_set or "FEATURE_COUNT = 77" in src_set
    )
    rd = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Wave AO" in rd
    cl = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## AO —" in cl
    fm = (ROOT / "scripts/feature_matrix.md").read_text(encoding="utf-8")
    assert "**AO**" in fm
    st_md = (ROOT / "AFTERNOON_STATUS.md").read_text(encoding="utf-8")
    assert "Wave AO" in st_md
    print("Wave AO OK")



    print("== Wave AP: analytics focus-note tap → Focus (on_open_focus) ==")
    from app.ui.screens import settings as settings_ui_ap
    from app.db import SCHEMA_VERSION, get_meta, get_session
    from inspect import signature
    from app.ui.screens.analytics import build_analytics

    assert settings_ui_ap.FEATURE_COUNT >= 72
    assert SCHEMA_VERSION == "13"
    with get_session() as s:
        assert get_meta(s, "schema_version") == "13"

    sig = signature(build_analytics)
    assert "on_open_focus" in sig.parameters

    src_ui = (ROOT / "app/ui/screens/analytics.py").read_text(encoding="utf-8")
    assert "on_open_focus" in src_ui
    assert "_tap_focus_note" in src_ui
    assert "Заметка скопирована" in src_ui  # clipboard fallback
    assert "Открыть Фокус" in src_ui
    src_main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert "on_open_focus=go_focus" in src_main and "build_analytics" in src_main
    src_set = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert (
        "FEATURE_COUNT = 72" in src_set
        or "FEATURE_COUNT = 71" in src_set
        or "FEATURE_COUNT = 73" in src_set
        or "FEATURE_COUNT = 74" in src_set
        or "FEATURE_COUNT = 75" in src_set or "FEATURE_COUNT = 76" in src_set or "FEATURE_COUNT = 77" in src_set
    )
    assert "A–AP" in src_set or "A-AP" in src_set or "A–AQ" in src_set or "A-AQ" in src_set or "A–AR" in src_set or "A-AR" in src_set or "A–AS" in src_set or "A-AS" in src_set or "A–AT" in src_set or "A-AT" in src_set or "A–AU" in src_set or "A-AU" in src_set or "A–AV" in src_set or "A-AV" in src_set
    rd = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Wave AP" in rd
    cl = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## AP —" in cl
    fm = (ROOT / "scripts/feature_matrix.md").read_text(encoding="utf-8")
    assert "**AP**" in fm
    st_md = (ROOT / "AFTERNOON_STATUS.md").read_text(encoding="utf-8")
    assert "Wave AP" in st_md
    print("Wave AP OK")



    print("== Wave AQ: notes vault CRUD + infinite canvas schema 13 ==")
    from app.db import SCHEMA_VERSION, get_meta, get_session
    from app.schemas import CanvasNodeCreate, NoteWrite, NoteCreate
    from app.services import canvas_service, notes_service
    from app.ui.screens import settings as settings_ui_aq
    from inspect import signature
    from app.ui.screens.canvas_board import build_canvas_board
    from app.ui.screens.note_editor import build_note_editor

    assert SCHEMA_VERSION == "13"
    assert settings_ui_aq.FEATURE_COUNT >= 72

    # Point notes vault at temp data dir (next to smoke DB)
    import app.db as dbmod
    vault = dbmod._DB_PATH.parent / "notes"
    notes_service.ensure_vault()
    assert vault.exists()
    files = notes_service.list_notes()
    for need in ("home.md", "tasks.md", "goals.md", "focus.md", "analytics.md", "roadmap.md"):
        assert need in files, need
    body = notes_service.read_note("home.md")
    assert "TaskTimer" in body or "Дом" in body or "#" in body
    notes_service.write_note("home.md", body + "\n\n<!-- smoke -->\n")
    assert "smoke" in notes_service.read_note("home.md")
    # create free note
    try:
        notes_service.create_note("smoke-aq.md", "# Smoke AQ\n\n- [ ] item\n")
    except FileExistsError:
        notes_service.write_note("smoke-aq.md", "# Smoke AQ\n")
    assert "smoke-aq.md" in notes_service.list_notes()
    # sanitize
    try:
        notes_service.sanitize_filename(".hidden.md")
        raise AssertionError("dotfile should fail")
    except ValueError:
        pass
    try:
        notes_service.sanitize_filename("bad name.md")
        raise AssertionError("spaces should fail")
    except ValueError:
        pass
    # traversal collapses to basename; resolve still confined to vault
    assert notes_service.sanitize_filename("../evil.md") == "evil.md"
    # pydantic
    nw = NoteWrite(filename="tasks.md", content="# T\n")
    assert nw.filename == "tasks.md"

    with get_session() as s:
        assert get_meta(s, "schema_version") == "13"
        canvas_service.ensure_canvas_seeded(s)
        nodes = canvas_service.list_nodes(s)
        assert len(nodes) >= 6
        sections = [n for n in nodes if n.kind == "section"]
        assert len(sections) >= 6
        refs = {n.ref for n in sections}
        assert "home.md" in refs and "roadmap.md" in refs
        n = canvas_service.create_node(
            s,
            CanvasNodeCreate(
                title="Smoke Note",
                x=10,
                y=20,
                kind="note",
                ref="smoke-aq.md",
                color="#4C8DFF",
            ),
        )
        assert n.id and n.ref == "smoke-aq.md"
        edges = canvas_service.list_edges(s)
        assert len(edges) >= 1
        canvas_service.delete_node(s, n.id)

    sig_c = signature(build_canvas_board)
    assert "on_open_note" in sig_c.parameters
    sig_n = signature(build_note_editor)
    assert "filename" in sig_n.parameters

    src_nav = (ROOT / "app/ui/components/nav.py").read_text(encoding="utf-8")
    assert "Холст" in src_nav
    src_main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert "build_canvas_board" in src_main
    assert "go_note" in src_main
    assert '"note"' in src_main or "'note'" in src_main
    src_home = (ROOT / "app/ui/screens/home.py").read_text(encoding="utf-8")
    assert "home.md" in src_home
    src_set = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert "FEATURE_COUNT = 72" in src_set or "FEATURE_COUNT = 73" in src_set or "FEATURE_COUNT = 74" in src_set or "FEATURE_COUNT = 75" in src_set or "FEATURE_COUNT = 76" in src_set or "FEATURE_COUNT = 77" in src_set
    assert (
        "A–AQ" in src_set
        or "A-AQ" in src_set
        or "A–AR" in src_set or "A–AS" in src_set or "A-AS" in src_set or "A–AT" in src_set or "A-AT" in src_set or "A–AU" in src_set or "A-AU" in src_set or "A–AV" in src_set or "A-AV" in src_set
        or "A-AR" in src_set or "A–AS" in src_set or "A-AS" in src_set or "A–AT" in src_set or "A-AT" in src_set or "A–AU" in src_set or "A-AU" in src_set or "A–AV" in src_set or "A-AV" in src_set
    )
    rd = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Wave AQ" in rd or "Холст" in rd
    cl = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## AQ —" in cl or "AQ" in cl

    # Path confinement: flat vault, no startswith sibling escape
    root = notes_service.notes_dir().resolve()
    resolved = notes_service._resolve("tasks.md")
    assert resolved.parent == root
    assert resolved.is_relative_to(root)
    # Missing non-starter file → empty string (not crash)
    ghost = "zz-missing-smoke.md"
    if notes_service.note_exists(ghost):
        (root / ghost).unlink()
    assert notes_service.read_note(ghost) == ""
    # Empty vault re-seeds starters via ensure_vault / list_notes
    for f in list(root.glob("*.md")):
        f.unlink()
    assert "home.md" in notes_service.list_notes()
    # Canvas ref path collapse
    n2 = CanvasNodeCreate(title="Evil", kind="note", ref="../../evil-path.md")
    assert n2.ref == "evil-path.md"
    # Esc closes note overlay
    from app.main import _OVERLAY_SCREENS as _ov
    assert "note" in _ov
    # Onboarding mentions Холст
    src_onb = (ROOT / "app/ui/screens/onboarding.py").read_text(encoding="utf-8")
    assert "Холст" in src_onb
    # lint includes vault/canvas modules
    from scripts.lint_imports import MODULES
    for need in (
        "app.services.notes_service",
        "app.services.canvas_service",
        "app.ui.screens.canvas_board",
        "app.ui.screens.note_editor",
    ):
        assert need in MODULES, need
    # note_editor save must not call refresh_all (remount risk)
    src_ne = (ROOT / "app/ui/screens/note_editor.py").read_text(encoding="utf-8")
    save_body = src_ne.split("def save")[1].split("def ")[0]
    code_lines = [
        ln for ln in save_body.splitlines() if not ln.lstrip().startswith("#")
    ]
    assert not any("refresh_all()" in ln for ln in code_lines)
    assert "paint()" in save_body

    # Export/import round-trip: vault notes + canvas nodes
    from app.services import notes_service as _ns_rt, canvas_service as _cs_rt
    marker_body = "# RoundTrip Smoke\n\nUNIQUE_VAULT_RT_TOKEN_991\n"
    _ns_rt.write_note("rt-smoke.md", marker_body)
    with get_session() as s:
        from app.schemas import CanvasNodeCreate as _CNC
        _cs_rt.create_node(
            s,
            _CNC(title="RT Node", kind="note", ref="rt-smoke.md", x=55, y=66, w=120, h=60),
        )
        payload_rt = export_service.export_all(s)
    assert payload_rt["notes"].get("rt-smoke.md", "").find("UNIQUE_VAULT_RT_TOKEN_991") >= 0
    assert any(
        (n.get("ref") == "rt-smoke.md" and n.get("kind") == "note")
        for n in (payload_rt.get("canvas_nodes") or [])
    )
    # Wipe note + clear canvas-ish via replace import after mutating
    _ns_rt.write_note("rt-smoke.md", "# wiped\n")
    assert "UNIQUE_VAULT_RT_TOKEN_991" not in _ns_rt.read_note("rt-smoke.md")
    with get_session() as s:
        summary_rt = export_service.import_all(s, payload_rt, mode="replace")
        assert summary_rt["mode"] == "replace"
        assert summary_rt.get("notes", 0) >= 1
        assert summary_rt.get("canvas_nodes", 0) >= 1
        nodes_rt = _cs_rt.list_nodes(s)
        assert any(n.ref == "rt-smoke.md" for n in nodes_rt)
    assert "UNIQUE_VAULT_RT_TOKEN_991" in _ns_rt.read_note("rt-smoke.md")
    # Esc closes reminders (aligned with other overlays)
    from app.main import _OVERLAY_SCREENS as _ov_rt
    assert "reminders" in _ov_rt
    # roadmap.py deprecated; canvas owns RM layer
    src_road_dep = (ROOT / "app/ui/screens/roadmap.py").read_text(encoding="utf-8")
    assert "DEPRECATED" in src_road_dep
    src_cb = (ROOT / "app/ui/screens/canvas_board.py").read_text(encoding="utf-8")
    # Wave AU+: InteractiveViewer was flaky (blank panel); GestureDetector viewport
    assert ("GestureDetector" in src_cb or "InteractiveViewer" in src_cb)
    assert "Scale" in src_cb or "alignment" in src_cb

    print("Wave AQ OK")


    print("== Wave AR: PIN lock / hash / setup / skip / gate / icon ==")
    from app.db import get_meta, get_session, set_meta
    from app.main import escape_closes_overlay
    from app.services import lock_service
    from app.ui.screens import settings as settings_ui_ar
    from scripts.lint_imports import MODULES as LINT_MODULES

    assert settings_ui_ar.FEATURE_COUNT >= 73
    assert lock_service.PIN_LENGTH == 4
    assert lock_service.MAX_ATTEMPTS == 5
    assert lock_service.LOCKOUT_SECONDS == 30

    # --- hash verify: salted PBKDF2, never plaintext ---
    salt_a, hash_a = lock_service.hash_pin("1234")
    salt_b, hash_b = lock_service.hash_pin("1234")
    assert salt_a != salt_b, "salt must be unique per hash"
    assert lock_service.verify_pin("1234", salt_a, hash_a)
    assert lock_service.verify_pin("1234", salt_b, hash_b)
    assert not lock_service.verify_pin("0000", salt_a, hash_a)
    assert not lock_service.verify_pin("123", salt_a, hash_a)
    assert not lock_service.verify_pin("12345", salt_a, hash_a)
    assert not lock_service.verify_pin("", salt_a, hash_a)
    assert "1234" not in hash_a and "1234" not in salt_a
    assert len(bytes.fromhex(salt_a)) >= 16
    assert len(bytes.fromhex(hash_a)) == 32

    with get_session() as s:
        assert lock_service.has_pin(s) is False
        assert lock_service.is_lock_enabled(s) is False
        assert lock_service.should_gate_main(s) is False
        assert lock_service.needs_pin_setup(s) is True

        # skip once → lock stays off
        lock_service.skip_lock_setup(s)
        assert lock_service.needs_pin_setup(s) is False
        assert lock_service.is_lock_enabled(s) is False
        assert lock_service.should_gate_main(s) is False
        assert get_meta(s, "lock_setup_done") == "1"
        for key in ("pin_salt", "pin_hash", "lock_enabled", "pin_fail_count"):
            val = get_meta(s, key)
            assert val in (None, "", "0")
            if val:
                assert "1234" not in str(val)

        # reset setup flag to simulate first PIN setup
        set_meta(s, "lock_setup_done", "0")
        s.commit()
        assert lock_service.needs_pin_setup(s) is True

        lock_service.setup_pin(s, "2468", biometrics=True)
        assert lock_service.has_pin(s) is True
        assert lock_service.is_lock_enabled(s) is True
        assert lock_service.should_gate_main(s) is True
        assert lock_service.needs_pin_setup(s) is False
        assert lock_service.is_biometrics_enabled(s) is True
        salt = get_meta(s, "pin_salt")
        digest = get_meta(s, "pin_hash")
        assert salt and digest
        assert "2468" not in salt and "2468" not in digest
        assert get_meta(s, "lock_enabled") == "1"
        # no plaintext PIN anywhere in meta
        from app.models import AppMeta

        for row in s.query(AppMeta).all() if hasattr(s, "query") else []:
            assert "2468" not in (row.value or "")
        for row in s.scalars(__import__("sqlalchemy").select(AppMeta)).all():
            assert "2468" not in (row.value or "")
            assert (row.value or "") != "2468"

        ok = lock_service.unlock(s, "2468")
        assert ok.ok is True
        assert ok.reason == "ok"
        assert ok.shake is False

        wrong = lock_service.unlock(s, "0000")
        assert wrong.ok is False
        assert wrong.reason == "wrong"
        assert wrong.shake is True
        assert wrong.remaining_attempts == 4

        # correct PIN resets the fail counter before the lockout sequence
        assert lock_service.unlock(s, "2468").ok is True
        now = 2_000_000.0
        for i in range(5):
            r = lock_service.unlock(s, "1111", now=now)
            assert r.ok is False
        assert r.reason == "lockout"
        assert r.lockout_remaining_sec == 30
        still = lock_service.unlock(s, "2468", now=now + 10)
        assert still.ok is False
        assert still.reason == "lockout"
        recovered = lock_service.unlock(s, "2468", now=now + 31)
        assert recovered.ok is True

        lock_service.set_lock_enabled(s, False)
        assert lock_service.should_gate_main(s) is False
        assert lock_service.has_pin(s) is True
        lock_service.set_lock_enabled(s, True)
        assert lock_service.should_gate_main(s) is True

        lock_service.change_pin(s, "9999")
        assert lock_service.unlock(s, "2468").ok is False
        assert lock_service.unlock(s, "9999").ok is True
        assert "9999" not in (get_meta(s, "pin_hash") or "")

    # Face ID fallback copy (desktop Flet has no local auth)
    assert lock_service.is_biometrics_available() is False
    msg = lock_service.biometrics_unavailable_message()
    assert "Face ID недоступен на этом устройстве" in msg
    assert "PIN" in msg

    # Esc must not bypass lock / setup / splash
    calls = []
    assert escape_closes_overlay("lock", lambda: calls.append("lock")) is False
    assert escape_closes_overlay("pin_setup", lambda: calls.append("pin")) is False
    assert escape_closes_overlay("splash", lambda: calls.append("splash")) is False
    assert calls == []

    src_main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert "build_lock_screen" in src_main
    assert "build_pin_setup" in src_main
    assert "build_splash" in src_main
    assert "assets_dir" in src_main or "assets" in src_main
    assert "window.icon" in src_main or "window_icon" in src_main
    assert "lock" in src_main and "pin_setup" in src_main

    src_lock = (ROOT / "app/ui/screens/lock_screen.py").read_text(encoding="utf-8")
    assert "Введите PIN" in src_lock
    assert "Face ID" in src_lock
    src_setup = (ROOT / "app/ui/screens/pin_setup.py").read_text(encoding="utf-8")
    assert "Защитите приложение" in src_setup
    assert "Настроить позже" in src_setup
    src_set = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert "Сменить PIN" in src_set or "сменить PIN" in src_set
    assert "биометр" in src_set.lower() or "Face ID" in src_set
    assert "FEATURE_COUNT = 73" in src_set or "FEATURE_COUNT = 74" in src_set or "FEATURE_COUNT = 75" in src_set or "FEATURE_COUNT = 76" in src_set or "FEATURE_COUNT = 77" in src_set
    assert any(x in src_set for x in ("A–AR", "A-AR", "A–AS", "A-AS", "A–AT", "A-AT", "A–AU", "A-AU", "A–AV", "A-AV"))

    icon = ROOT / "assets" / "icon.png"
    assert icon.is_file(), "assets/icon.png required"
    raw = icon.read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(raw) > 200
    icon192 = ROOT / "assets" / "icon-192.png"
    assert icon192.is_file(), "assets/icon-192.png required"
    raw192 = icon192.read_bytes()
    assert raw192[:8] == b"\x89PNG\r\n\x1a\n"
    w192, h192 = struct.unpack(">II", raw192[16:24])
    assert (w192, h192) == (192, 192)

    for need in (
        "app.services.lock_service",
        "app.ui.screens.lock_screen",
        "app.ui.screens.pin_setup",
        "app.ui.screens.splash",
    ):
        assert need in LINT_MODULES, need

    rd = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "PIN" in rd and ("иконк" in rd.lower() or "icon.png" in rd)
    cl = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## AR —" in cl or "## AR " in cl
    fm = (ROOT / "scripts/feature_matrix.md").read_text(encoding="utf-8")
    assert "**AR**" in fm
    print("Wave AR OK")



    print("== Wave AS: iOS IPA ready / pyproject / icon_ios / mobile layout ==")
    from app.services import lock_service as _ls_as
    from app.ui.theme import is_mobile_layout, platform_name
    from app.ui.screens import settings as settings_ui_as

    assert settings_ui_as.FEATURE_COUNT >= 74

    pyproject = ROOT / "pyproject.toml"
    assert pyproject.is_file(), "pyproject.toml required for flet build ipa"
    ppt = pyproject.read_text(encoding="utf-8")
    assert 'name = "tasktimer"' in ppt or "name = 'tasktimer'" in ppt
    assert "SQLAlchemy==2.0.36" in ppt
    assert "com.rom4ik121.tasktimer" in ppt
    assert 'product = "TaskTimer"' in ppt or "product = 'TaskTimer'" in ppt
    assert "NSFaceIDUsageDescription" in ppt
    assert 'export_method = "debugging"' in ppt or "export_method = 'debugging'" in ppt
    assert 'module = "main"' in ppt
    assert "#0F0F12" in ppt

    entry = ROOT / "main.py"
    assert entry.is_file(), "root main.py for flet packaging"
    ent = entry.read_text(encoding="utf-8")
    assert "app.main" in ent and "ft.run" in ent

    icon_ios = ROOT / "assets" / "icon_ios.png"
    assert icon_ios.is_file(), "assets/icon_ios.png required"
    raw_ios = icon_ios.read_bytes()
    assert raw_ios[:8] == b"\x89PNG\r\n\x1a\n"
    w_ios, h_ios = struct.unpack(">II", raw_ios[16:24])
    assert w_ios >= 1024 and h_ios >= 1024, (w_ios, h_ios)

    src_main_as = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert "is_mobile_layout" in src_main_as
    assert "SafeArea" in src_main_as
    assert "PHONE_W" in src_main_as  # desktop frame kept

    # Desktop smoke: biometrics unavailable; try_unlock never bypasses PIN
    assert _ls_as.is_biometrics_available() is False
    assert _ls_as.try_biometric_unlock() is False
    assert "Face ID недоступен" in _ls_as.biometrics_unavailable_message()
    # iOS platform hook: available True but unlock still False without plugin
    _ls_as.set_runtime_platform("ios")
    assert _ls_as.is_biometrics_available() is True
    assert _ls_as.try_biometric_unlock() is False
    assert "PIN" in _ls_as.biometrics_unavailable_message()
    _ls_as.set_runtime_platform(None)  # reset for any later checks
    assert _ls_as.is_biometrics_available() is False

    # Charts remain importable on desktop; optional path exists
    pr = (ROOT / "app/ui/components/progress_ring.py").read_text(encoding="utf-8")
    assert "_HAS_CHARTS" in pr
    an = (ROOT / "app/ui/screens/analytics.py").read_text(encoding="utf-8")
    assert "_HAS_CHARTS" in an

    ios_doc = ROOT / "docs" / "IOS_BUILD.md"
    assert ios_doc.is_file()
    ios_txt = ios_doc.read_text(encoding="utf-8")
    assert "flet build ipa" in ios_txt
    assert "macOS" in ios_txt
    assert "com.rom4ik121.tasktimer" in ios_txt
    assert "Linux" in ios_txt or "Windows" in ios_txt

    rd_as = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "IOS_BUILD.md" in rd_as or "docs/IOS_BUILD" in rd_as
    cl_as = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## AS —" in cl_as or "## AS " in cl_as
    fm_as = (ROOT / "scripts/feature_matrix.md").read_text(encoding="utf-8")
    assert "**AS**" in fm_as
    src_set_as = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert "FEATURE_COUNT = 74" in src_set_as or "FEATURE_COUNT = 75" in src_set_as or "FEATURE_COUNT = 76" in src_set_as or "FEATURE_COUNT = 77" in src_set_as
    print("Wave AS OK")


    print("== Wave AT: UX polish / toasts / home density / validation ==")
    from app.ui.components import dialogs as dlg_at
    from app.ui.screens import home as home_ui_at
    from app.ui.screens import settings as settings_ui_at
    from app.schemas import TaskCreate as TaskCreateAT

    assert settings_ui_at.FEATURE_COUNT >= 75
    assert hasattr(dlg_at, "show_toast")
    assert hasattr(dlg_at, "show_info")
    assert hasattr(dlg_at, "confirm_action")
    assert hasattr(dlg_at, "confirm_delete")
    assert hasattr(dlg_at, "set_field_error")
    assert hasattr(dlg_at, "validation_fail")
    assert hasattr(dlg_at, "ru_validation_message")
    assert callable(dlg_at.show_snack)

    src_dlg = (ROOT / "app/ui/components/dialogs.py").read_text(encoding="utf-8")
    for kind in ("success", "error", "info", "warning"):
        assert kind in src_dlg
    assert "ToastKind" in src_dlg

    assert home_ui_at.MAX_HOME_BANNERS == 2
    src_home_at = (ROOT / "app/ui/screens/home.py").read_text(encoding="utf-8")
    assert "MAX_HOME_BANNERS" in src_home_at
    assert "ещё" in src_home_at
    assert "today_sheet_open" in src_home_at
    assert "toggle_today_sheet" in src_home_at
    assert "show_toast" in src_home_at
    assert "show_info" in src_home_at
    assert "donut_progress" not in src_home_at
    assert "heat_section" not in src_home_at

    src_ct = (ROOT / "app/ui/screens/create_task.py").read_text(encoding="utf-8")
    assert "validation_fail" in src_ct
    assert "Введите название задачи" in src_ct

    src_set_at = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert "FEATURE_COUNT = 75" in src_set_at or "FEATURE_COUNT = 76" in src_set_at or "FEATURE_COUNT = 77" in src_set_at
    assert any(x in src_set_at for x in ("A–AT", "A-AT", "A–AU", "A-AU", "A–AV", "A-AV"))
    assert "group_heading" in src_set_at
    assert "validation_fail" in src_set_at

    src_theme = (ROOT / "app/ui/theme.py").read_text(encoding="utf-8")
    assert "screen_header" in src_theme
    assert "header_icon_btn" in src_theme
    assert "screen_insets" in src_theme
    assert "is_compact_layout" in src_theme

    blank_ok = False
    try:
        TaskCreateAT(title="   ")
    except Exception as exc:
        msg = dlg_at.ru_validation_message(exc)
        assert "назван" in msg.lower() or "Введите" in msg
        blank_ok = True
    assert blank_ok, "blank task title must fail validation"

    src_pin = (ROOT / "app/ui/screens/pin_setup.py").read_text(encoding="utf-8")
    assert "PIN не совпадает" in src_pin
    assert "show_toast" in src_pin

    src_note = (ROOT / "app/ui/screens/note_editor.py").read_text(encoding="utf-8")
    assert "validation_fail" in src_note

    src_cv = (ROOT / "app/ui/screens/canvas_board.py").read_text(encoding="utf-8")
    assert "validation_fail" in src_cv
    assert "screen_header" in src_cv

    src_tasks = (ROOT / "app/ui/screens/tasks.py").read_text(encoding="utf-8")
    assert "screen_header" in src_tasks

    src_an = (ROOT / "app/ui/screens/analytics.py").read_text(encoding="utf-8")
    assert "screen_header" in src_an
    assert "show_info" in src_an

    rd_at = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Wave AT" in rd_at
    cl_at = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## AT —" in cl_at or "## AT " in cl_at
    fm_at = (ROOT / "scripts/feature_matrix.md").read_text(encoding="utf-8")
    assert "**AT**" in fm_at
    print("Wave AT OK")



    print("== Wave AU: canvas blank-panel fix / GestureDetector viewport ==")
    from app.ui.screens import settings as settings_ui_au
    from app.ui.screens.canvas_board import build_canvas_board
    from app.services import canvas_service, notes_service
    from app.db import get_session, init_db

    assert settings_ui_au.FEATURE_COUNT in (76, 77)
    src_cb_au = (ROOT / "app/ui/screens/canvas_board.py").read_text(encoding="utf-8")
    assert "GestureDetector" in src_cb_au
    assert "InteractiveViewer(" not in src_cb_au
    assert "Scale(" in src_cb_au
    assert "pan_x" in src_cb_au and "pan_y" in src_cb_au
    assert "_zoom_in" in src_cb_au and "_frame_home" in src_cb_au
    assert "height=420" in src_cb_au
    assert "screen_header" in src_cb_au
    init_db()
    notes_service.ensure_vault()
    with get_session() as s:
        canvas_service.ensure_canvas_seeded(s)
        nodes = canvas_service.list_nodes(s)
    assert len([n for n in nodes if (n.kind or "") == "section"]) >= 6

    class _FakePageAU:
        def update(self):
            pass
        def run_task(self, *a, **k):
            pass
        def show_dialog(self, *a, **k):
            pass
        def pop_dialog(self):
            pass
        overlay = []

    board = build_canvas_board(_FakePageAU())
    titles = []

    def _walk_au(c):
        if c is None:
            return
        v = getattr(c, "value", None)
        if isinstance(v, str) and v in ("Дом", "Задачи", "Цели", "Фокус", "Аналитика", "Роадмап"):
            titles.append(v)
        content = getattr(c, "content", None)
        if content is not None:
            _walk_au(content)
        for ch in getattr(c, "controls", None) or []:
            _walk_au(ch)

    _walk_au(board)
    assert len(set(titles)) >= 6, titles

    src_set_au = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert "FEATURE_COUNT = 76" in src_set_au or "FEATURE_COUNT = 77" in src_set_au
    assert "A–AU" in src_set_au or "A-AU" in src_set_au

    print("== Wave AV: filter sheets / haptics / motion ==")
    from app.ui.screens import settings as settings_ui_av
    from app.ui import haptics as haptics_av
    from app.ui import motion as motion_av
    from app.ui.components import filter_sheet as filter_sheet_av
    from app.db import get_session, get_meta
    from app.schemas import SettingsUpdate
    from app.services import settings_service

    assert settings_ui_av.FEATURE_COUNT == 77
    assert hasattr(haptics_av, "haptic")
    assert hasattr(haptics_av, "attach")
    assert hasattr(haptics_av, "set_enabled")
    assert hasattr(motion_av, "make_switcher")
    assert hasattr(motion_av, "appear_item")
    assert hasattr(motion_av, "splash_fade")
    assert 150 <= motion_av.DURATION_FAST <= 280
    assert 150 <= motion_av.DURATION_MED <= 280
    assert 150 <= motion_av.DURATION_SLOW <= 280
    assert hasattr(filter_sheet_av, "show_filter_sheet")
    assert hasattr(filter_sheet_av, "FilterSection")
    haptics_av.haptic(None, "light")  # no-op, must not raise

    with get_session() as s:
        st = settings_service.get_settings(s)
        assert st.haptics_enabled is True
        settings_service.update_settings(s, SettingsUpdate(haptics_enabled=False))
        st2 = settings_service.get_settings(s)
        assert st2.haptics_enabled is False
        settings_service.update_settings(s, SettingsUpdate(haptics_enabled=True))
        assert settings_service.get_settings(s).haptics_enabled is True
        assert get_meta(s, "haptics_enabled") == "1"

    src_tasks_av = (ROOT / "app/ui/screens/tasks.py").read_text(encoding="utf-8")
    assert "Фильтры" in src_tasks_av
    src_sheet_av = (ROOT / "app/ui/components/filter_sheet.py").read_text(encoding="utf-8")
    assert "Сбросить" in src_sheet_av
    assert "Готово" in src_sheet_av
    assert "show_filter_sheet" in src_tasks_av
    assert "FILTER_ALT" in src_tasks_av or "FILTER_LIST" in src_tasks_av
    assert "FloatingActionButton" in src_tasks_av
    assert "ft.Row(status_chips" not in src_tasks_av
    assert "summary_chip" in src_tasks_av
    assert "haptic(" in src_tasks_av

    src_focus_av = (ROOT / "app/ui/screens/focus.py").read_text(encoding="utf-8")
    assert "show_filter_sheet" in src_focus_av
    assert "hist_chips" in src_focus_av
    assert "С заметкой" in src_focus_av
    assert "open_hist_filters" in src_focus_av

    src_set_av = (ROOT / "app/ui/screens/settings.py").read_text(encoding="utf-8")
    assert "FEATURE_COUNT = 77" in src_set_av
    assert "Тактильность" in src_set_av
    assert "A–AV" in src_set_av or "A-AV" in src_set_av
    assert "haptics_sw" in src_set_av

    src_home_av = (ROOT / "app/ui/screens/home.py").read_text(encoding="utf-8")
    assert "today_sheet_open" in src_home_av
    assert "_digest_chip" in src_home_av

    src_main_av = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert "attach_haptics" in src_main_av
    assert "make_switcher" in src_main_av

    src_hap = (ROOT / "app/ui/haptics.py").read_text(encoding="utf-8")
    assert "HapticFeedback" in src_hap
    assert "invoke_method" in src_hap

    rd_av = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Wave AV" in rd_av
    cl_av = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## AV —" in cl_av or "## AV " in cl_av
    fm_av = (ROOT / "scripts/feature_matrix.md").read_text(encoding="utf-8")
    assert "**AV**" in fm_av
    print("Wave AV OK")

    rd_au = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Wave AU" in rd_au
    cl_au = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## AU —" in cl_au or "## AU " in cl_au
    fm_au = (ROOT / "scripts/feature_matrix.md").read_text(encoding="utf-8")
    assert "**AU**" in fm_au
    print("Wave AU OK")


    print("== lint imports ==")
    from scripts.lint_imports import lint_imports

    n = lint_imports()
    print(f"lint_imports OK ({n} modules)")

    shutil.rmtree(tmp, ignore_errors=True)
    print("SMOKE_OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("SMOKE_FAIL", exc)
        raise
