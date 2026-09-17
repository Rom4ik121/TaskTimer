"""Seed sample data on first run only (app_meta.seeded guard)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from app.db import SCHEMA_VERSION, get_session, is_empty, set_meta
from app.models import Goal, ProgressLog, RoadmapEdge, RoadmapNode, Subtask, Task


def seed_if_empty() -> None:
    if not is_empty():
        return
    with get_session() as session:
        book = Goal(
            title="Прочитать книгу",
            description="Atomic Habits — 10 страниц в день",
            target_value=250,
            unit="страниц",
            daily_quota=10,
            current_value=0,
        )
        fitness = Goal(
            title="Фитнес-челлендж",
            description="30 тренировок за квартал",
            target_value=30,
            unit="тренировок",
            daily_quota=1,
            current_value=0,
        )
        code = Goal(
            title="Изучить Flet",
            description="40 часов практики UI",
            target_value=40,
            unit="часов",
            daily_quota=1.5,
            current_value=0,
        )
        session.add_all([book, fitness, code])
        session.flush()

        today = date.today()
        now = datetime.now()
        tasks = [
            Task(
                title="Утренний обзор целей",
                description="Проверить прогресс по книге и фитнесу",
                status="done",
                priority="medium",
                due_date=today - timedelta(days=1),
                goal_id=book.id,
                color_tag="оранжевый",
                completed_at=now - timedelta(days=1),
            ),
            Task(
                title="Прочитать 10 страниц",
                description="Глава 4 — Atomic Habits",
                status="in_progress",
                priority="high",
                due_date=today,
                goal_id=book.id,
                color_tag="синий",
            ),
            Task(
                title="Силовая тренировка",
                description="45 минут: спина + кор",
                status="todo",
                priority="high",
                due_date=today,
                goal_id=fitness.id,
                color_tag="зелёный",
            ),
            Task(
                title="Сверстать экран Analytics",
                description="Линейный график 14 дней + donut",
                status="in_progress",
                priority="medium",
                due_date=today + timedelta(days=1),
                goal_id=code.id,
            ),
            Task(
                title="Ревью roadmap",
                description="Связать узлы спринта",
                status="todo",
                priority="low",
                due_date=today + timedelta(days=2),
            ),
            Task(
                title="Вечерний лог прогресса",
                description="Записать страницы и тренировку",
                status="done",
                priority="medium",
                due_date=today - timedelta(days=2),
                completed_at=now - timedelta(days=2),
            ),
            Task(
                title="Подготовить seed-данные",
                description="Примеры целей и задач",
                status="done",
                priority="low",
                due_date=today - timedelta(days=3),
                completed_at=now - timedelta(days=3),
            ),
        ]
        session.add_all(tasks)
        session.flush()

        # Sample checklist on reading task
        session.add_all(
            [
                Subtask(task_id=tasks[1].id, title="Открыть главу", done=True, position=0),
                Subtask(task_id=tasks[1].id, title="Прочитать 10 стр.", done=False, position=1),
                Subtask(task_id=tasks[1].id, title="Записать заметку", done=False, position=2),
                Subtask(task_id=tasks[2].id, title="Разминка", done=False, position=0),
                Subtask(task_id=tasks[2].id, title="Основной блок", done=False, position=1),
            ]
        )

        for i in range(8):
            session.add(
                ProgressLog(
                    goal_id=book.id,
                    amount=10,
                    note=f"День {i + 1}",
                    logged_at=now - timedelta(days=8 - i),
                )
            )
        for i in range(5):
            session.add(
                ProgressLog(
                    goal_id=fitness.id,
                    amount=1,
                    note="Тренировка",
                    logged_at=now - timedelta(days=10 - i * 2),
                )
            )
        # Today partial quota for book so Home «Сегодня» shows incomplete
        session.add(
            ProgressLog(
                goal_id=book.id,
                amount=4,
                note="Сегодня утром",
                logged_at=now,
            )
        )

        nodes = [
            RoadmapNode(title="Идея", x=40, y=180, status="done", task_id=tasks[6].id),
            RoadmapNode(title="MVP UI", x=160, y=80, status="done", task_id=tasks[0].id),
            RoadmapNode(title="Цели", x=160, y=260, status="active", task_id=tasks[1].id),
            RoadmapNode(title="Аналитика", x=300, y=80, status="active", task_id=tasks[3].id),
            RoadmapNode(title="Roadmap", x=300, y=260, status="pending", task_id=tasks[4].id),
            RoadmapNode(title="Релиз", x=440, y=170, status="pending"),
        ]
        session.add_all(nodes)
        session.flush()
        edges = [
            RoadmapEdge(from_node_id=nodes[0].id, to_node_id=nodes[1].id),
            RoadmapEdge(from_node_id=nodes[0].id, to_node_id=nodes[2].id),
            RoadmapEdge(from_node_id=nodes[1].id, to_node_id=nodes[3].id),
            RoadmapEdge(from_node_id=nodes[2].id, to_node_id=nodes[4].id),
            RoadmapEdge(from_node_id=nodes[3].id, to_node_id=nodes[5].id),
            RoadmapEdge(from_node_id=nodes[4].id, to_node_id=nodes[5].id),
        ]
        session.add_all(edges)
        session.flush()

        # Align current_value with sum of ProgressLog amounts
        from sqlalchemy import func, select
        from app.models import ProgressLog as PL

        for g in (book, fitness, code):
            total = session.scalar(
                select(func.coalesce(func.sum(PL.amount), 0.0)).where(PL.goal_id == g.id)
            )
            g.current_value = float(total or 0.0)

        # Vault MD + canvas section nodes
        from app.services import canvas_service, notes_service

        notes_service.ensure_vault()
        canvas_service.seed_section_nodes(session, commit=False)

        # Mark seeded BEFORE commit so wipe never re-seeds
        set_meta(session, "seeded", "1")
        set_meta(session, "schema_version", SCHEMA_VERSION)
        set_meta(session, "display_name", "Рома")
        set_meta(session, "accent_hex", "#FF8A00")
        set_meta(session, "week_starts_monday", "1")
        session.commit()
