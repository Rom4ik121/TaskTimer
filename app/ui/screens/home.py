"""Home dashboard — today quotas, goals, tasks, focus entry, settings."""
from __future__ import annotations

import time

import flet as ft
from pydantic import ValidationError

from app.db import get_session
from app.schemas import ProgressLogCreate
from app.services import (
    analytics_service,
    export_service,
    goal_service,
    settings_service,
    streak_service,
    task_service,
    timer_service,
)
from app.services.goal_service import add_progress
from app.ui.components.cards import (
    empty_state,
    goal_card,
    streak_badge_chip,
    task_card,
    today_quota_card,
)
from app.ui.components.dialogs import (
    confirm_delete,
    show_info,
    show_toast,
    validation_fail,
)
from app.ui.components.progress_ring import mini_ring
from app.ui.haptics import haptic
from app.ui.screens.onboarding import maybe_show_onboarding
from app.ui.theme import (
    BORDER,
    MUTED,
    ORANGE,
    RED,
    TEXT,
    card_style,
    header_icon_btn,
    is_compact_layout,
    muted,
    screen_insets,
    section_title,
)

# Cap simultaneous Home banners; the rest sit behind «ещё» / Reminders.
MAX_HOME_BANNERS = 2


def build_home(
    page: ft.Page,
    *,
    on_add,
    refresh_all,
    on_open_task=None,
    on_open_goal=None,
    on_open_focus=None,
    on_open_settings=None,
    on_open_overdue=None,
    on_open_reminders=None,
    on_open_due_today=None,
    on_open_search=None,
    on_open_note=None,
) -> ft.Control:
    body = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)
    # Wave X: undo last quick progress log (30s window); page-local state
    undo_state: dict = {"log_id": None, "ts": 0.0, "goal_id": None}
    today_sheet_open = {"value": False}

    def reload(_: ft.ControlEvent | None = None):
        body.controls.clear()
        with get_session() as session:
            # Wave Y: goals by % desc (most complete first)
            goals = goal_service.list_goals(session, sort="percent")
            quotas = goal_service.today_quotas(session)
            # One tasks query (selectinload subtasks); derive active / overdue / due_today
            all_active = task_service.list_tasks(session, archived=False)
            # pinned already sorted first by list_tasks smart sort
            tasks = [t for t in all_active if t.status != "done"][:5]
            overdue_tasks = [t for t in all_active if task_service.is_overdue(t)]
            due_today_tasks = [t for t in all_active if task_service.is_due_today(t)]
            active_timer = timer_service.get_active_session(session)
            if active_timer and active_timer.status == "running":
                active_timer = timer_service.tick(session, active_timer.id) or active_timer
            streaks = streak_service.all_streaks(session)
            settings = settings_service.get_settings(session)
            week_sum = task_service.week_due_summary(
                session, week_starts_monday=settings.week_starts_monday
            )
            # Reminder count without re-querying tasks/quotas
            rem_count = (
                len(due_today_tasks)
                + len(overdue_tasks)
                + sum(1 for q in quotas if not q.get("complete"))
            )
            quiet = settings_service.is_quiet_hours(settings)
            wind_down = settings_service.is_wind_down(settings)
            week_done, week_target = analytics_service.weekly_goal_progress(session)
            home_tip = settings_service.get_daily_home_tip(session)
            backup_due = export_service.needs_backup_reminder(session, days=7)
            backup_dismissed = export_service.is_backup_tip_dismissed(session)
            today_est = task_service.today_estimate_minutes(session)
            momentum = analytics_service.momentum_score(session)
            stuck = analytics_service.stuck_goals(session, days=3)
            suggest_dismissed = settings_service.is_smart_suggest_dismissed(session)
            daily_note = settings_service.get_daily_note(session)
            last_done_id = None
            last_done_title = None
            from app.db import get_meta
            raw_lid = get_meta(session, "last_completed_task_id")
            if raw_lid:
                try:
                    lid = int(str(raw_lid).strip())
                except (TypeError, ValueError):
                    lid = None
                if lid is not None:
                    lt = task_service.get_task(session, lid)
                    if lt and lt.status == "done" and not getattr(lt, "archived", False):
                        last_done_id = lt.id
                        last_done_title = lt.title

        streak_map = {s.goal_id: s.current_streak for s in streaks}

        display = settings.display_name or "Рома"
        compact = bool(getattr(settings, "compact_ui", False))
        dense = is_compact_layout(page, compact_ui=compact)
        body.spacing = 8 if dense else 12

        done_q = sum(1 for q in quotas if q.get("complete"))
        total_q = len(quotas)
        best_streak = max((s.best_streak for s in streaks), default=0) if streaks else 0

        def toggle_today_sheet(_e=None):
            today_sheet_open["value"] = not today_sheet_open["value"]
            reload()

        def _mini_chip(
            label: str,
            value: str,
            *,
            accent: bool = False,
            on_click=None,
            tooltip: str | None = None,
        ) -> ft.Control:
            return ft.Container(
                content=ft.Row(
                    [
                        ft.Text(label, size=10, color=MUTED),
                        ft.Text(
                            value,
                            size=12,
                            weight=ft.FontWeight.W_700,
                            color=ORANGE if accent else TEXT,
                        ),
                    ],
                    spacing=6,
                    tight=True,
                ),
                padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                bgcolor="#1C1C22",
                border=ft.Border.all(1, ORANGE if accent else "#2A2A32"),
                border_radius=ft.BorderRadius.all(20),
                on_click=on_click,
                ink=bool(on_click),
                tooltip=tooltip,
            )

        quota_chip = _mini_chip(
            "Квоты",
            f"{done_q}/{total_q}" if total_q else "—",
            accent=total_q > 0 and done_q == total_q,
            on_click=toggle_today_sheet,
            tooltip="Сегодня · квоты",
        )
        streak_chip = _mini_chip(
            "Рекорд",
            f"🔥 {best_streak}" if best_streak else "—",
            accent=best_streak > 0,
            on_click=toggle_today_sheet,
            tooltip="Сегодня · серии",
        )

        mom_color = ORANGE if momentum.score >= 60 else (MUTED if momentum.score < 35 else "#4C8DFF")
        momentum_chip = ft.Container(
            content=ft.Row(
                [
                    mini_ring(float(momentum.score), color=mom_color, size=26),
                    ft.Column(
                        [
                            ft.Text("Импульс", size=10, color=MUTED),
                            ft.Text(
                                str(momentum.score),
                                size=12,
                                weight=ft.FontWeight.W_700,
                                color=ORANGE if momentum.score >= 60 else TEXT,
                            ),
                        ],
                        spacing=0,
                        tight=True,
                    ),
                ],
                spacing=8,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            bgcolor="#1C1C22",
            border=ft.Border.all(1, ORANGE if momentum.score >= 60 else "#2A2A32"),
            border_radius=ft.BorderRadius.all(20),
            tooltip=(
                f"Квоты {momentum.quotas_pct:.0f}% · "
                f"задачи {momentum.completion_pct:.0f}% · "
                f"серия {momentum.streak_pct:.0f}%"
            ),
            on_click=None,
            ink=True,
        )

        active_n = sum(1 for t in all_active if t.status != "done")
        tasks_chip = _mini_chip(
            "Задачи",
            str(active_n),
            accent=active_n > 0,
            tooltip="Активные задачи ниже",
        )

        rem_badge = None
        if rem_count:
            rem_badge = ft.Container(
                content=ft.Text(
                    str(rem_count) if rem_count < 10 else "9+",
                    size=9,
                    weight=ft.FontWeight.W_700,
                    color="#0F0F12",
                ),
                bgcolor=ORANGE,
                width=16,
                height=16,
                border_radius=ft.BorderRadius.all(8),
                alignment=ft.Alignment.CENTER,
                right=2,
                top=2,
            )
        icon_size = 36 if dense else 40
        header_actions: list[ft.Control] = [
            header_icon_btn(
                ft.Icons.NOTIFICATIONS_NONE,
                on_click=lambda e: on_open_reminders() if on_open_reminders else None,
                tooltip="Напоминания",
                size=icon_size,
                badge=rem_badge,
                border_color=ORANGE if rem_count else BORDER,
            ),
        ]
        if not dense:
            header_actions.append(
                header_icon_btn(
                    ft.Icons.SEARCH,
                    on_click=lambda e: on_open_search() if on_open_search else None,
                    tooltip="Поиск",
                    size=icon_size,
                )
            )
        header_actions.extend(
            [
                header_icon_btn(
                    ft.Icons.SETTINGS_OUTLINED,
                    on_click=lambda e: on_open_settings() if on_open_settings else None,
                    tooltip="Настройки",
                    size=icon_size,
                ),
                header_icon_btn(
                    ft.Icons.ADD_ROUNDED,
                    on_click=lambda e: on_add(),
                    tooltip="Создать",
                    accent=True,
                    size=icon_size,
                    icon_size=22,
                ),
            ]
        )
        header = ft.Column(
            [
                ft.Row(
                    [
                        ft.Column(
                            [
                                muted(f"Привет, {display}"),
                                ft.Text(
                                    "Сегодня",
                                    size=22 if dense else 24,
                                    weight=ft.FontWeight.W_700,
                                    color=TEXT,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        *header_actions,
                    ],
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    [quota_chip, streak_chip, momentum_chip, tasks_chip],
                    spacing=8,
                    wrap=True,
                    run_spacing=6,
                ),
                *(
                    [muted(f"Оценка на сегодня: {today_est} мин")]
                    if today_est > 0
                    else []
                ),
            ],
            spacing=8,
        )


        tip_line = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.LIGHTBULB_OUTLINE, color=ORANGE, size=14),
                    ft.Text(
                        home_tip,
                        size=11,
                        color=MUTED,
                        expand=True,
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=4, vertical=2),
        )

        backup_tip = None
        if backup_due and not backup_dismissed:
            def _dismiss_backup(_e=None):
                try:
                    with get_session() as session:
                        export_service.dismiss_backup_tip(session)
                        if not export_service.is_backup_tip_dismissed(session):
                            export_service.clear_backup_tip_dismiss(session)
                            export_service.dismiss_backup_tip(session)
                except Exception:
                    try:
                        with get_session() as session:
                            export_service.clear_backup_tip_dismiss(session)
                            export_service.dismiss_backup_tip(session)
                    except Exception:
                        pass
                reload()

            backup_tip = ft.Container(
                content=ft.Row(
                    [
                        ft.Container(
                            content=ft.Row(
                                [
                                    ft.Icon(ft.Icons.BACKUP_OUTLINED, color=MUTED, size=14),
                                    ft.Text(
                                        "Сделайте экспорт бэкапа",
                                        size=11,
                                        color=MUTED,
                                        expand=True,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                ],
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            expand=True,
                            on_click=lambda e: on_open_settings() if on_open_settings else None,
                            ink=True,
                            tooltip="Настройки → Резервная копия",
                        ),
                        ft.Container(
                            content=ft.Icon(ft.Icons.CLOSE, color=MUTED, size=14),
                            width=28,
                            height=28,
                            alignment=ft.Alignment.CENTER,
                            on_click=_dismiss_backup,
                            tooltip="Скрыть сегодня",
                            ink=True,
                        ),
                    ],
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.symmetric(horizontal=4, vertical=2),
            )

        suggestion = None
        if not suggest_dismissed:
            incomplete_quotas = [
                (q["goal"].title, q["goal"].id)
                for q in quotas
                if not q.get("complete")
            ]
            suggestion = analytics_service.compute_smart_suggestion(
                stuck=stuck,
                overdue_count=len(overdue_tasks),
                incomplete_quotas=incomplete_quotas,
            )

        smart_card = None
        if suggestion and (suggestion.text or "").strip():
            kind = suggestion.kind
            gid = suggestion.goal_id

            def _dismiss_suggest(_e=None):
                try:
                    with get_session() as session:
                        settings_service.dismiss_smart_suggest(session)
                        if not settings_service.is_smart_suggest_dismissed(session):
                            # write may have been skipped on corrupt meta — force
                            settings_service.clear_smart_suggest_dismiss(session)
                            settings_service.dismiss_smart_suggest(session)
                except Exception:
                    try:
                        with get_session() as session:
                            settings_service.clear_smart_suggest_dismiss(session)
                            settings_service.dismiss_smart_suggest(session)
                    except Exception:
                        pass
                reload()

            def _tap_suggest(_e=None):
                try:
                    if kind == "overdue":
                        if on_open_overdue:
                            on_open_overdue()
                    elif gid is not None and on_open_goal:
                        on_open_goal(gid)
                except Exception:
                    pass

            smart_card = ft.Container(
                content=ft.Row(
                    [
                        ft.Container(
                            content=ft.Row(
                                [
                                    ft.Icon(
                                        ft.Icons.TIPS_AND_UPDATES_OUTLINED,
                                        color=ORANGE,
                                        size=16,
                                    ),
                                    ft.Text(
                                        suggestion.text,
                                        size=12,
                                        color=TEXT,
                                        expand=True,
                                        max_lines=2,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                ],
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            expand=True,
                            on_click=_tap_suggest,
                            ink=True,
                        ),
                        ft.Container(
                            content=ft.Icon(ft.Icons.CLOSE, color=MUTED, size=14),
                            width=28,
                            height=28,
                            alignment=ft.Alignment.CENTER,
                            on_click=_dismiss_suggest,
                            tooltip="Скрыть сегодня",
                            ink=True,
                        ),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                bgcolor="#2A1C12",
                border=ft.Border.all(1, ORANGE),
                border_radius=ft.BorderRadius.all(14),
            )

        def _offer_undo_snack(log, message: str) -> None:
            if log is None:
                show_toast(page, message, kind="success")
                return
            undo_state["log_id"] = int(log.id)
            undo_state["ts"] = time.time()
            undo_state["goal_id"] = int(log.goal_id)

            def do_undo(_e=None):
                lid = undo_state.get("log_id")
                ts = float(undo_state.get("ts") or 0)
                if not lid or (time.time() - ts) > 30:
                    show_toast(page, "Слишком поздно отменять", kind="warning")
                    return
                with get_session() as session:
                    ok = goal_service.delete_log(session, int(lid))
                undo_state["log_id"] = None
                undo_state["ts"] = 0.0
                if ok:
                    show_toast(page, "Лог отменён", kind="success")
                    reload()
                    page.update()
                else:
                    show_toast(page, "Лог уже удалён", kind="error")

            show_toast(
                page,
                message,
                kind="success",
                action_label="Отменить",
                on_action=do_undo,
                duration_ms=30_000,
            )

        def on_progress(goal_id: int):
            def submit(e):
                raw = amount_field.value or "1"
                try:
                    amount = float(str(raw).replace(",", "."))
                except ValueError:
                    validation_fail(page, "Введите число", amount_field)
                    return
                try:
                    payload = ProgressLogCreate(
                        goal_id=goal_id, amount=amount, note="Быстрый лог"
                    )
                except ValidationError:
                    validation_fail(page, "Сумма должна быть больше 0", amount_field)
                    return
                with get_session() as session:
                    log = add_progress(session, payload)
                    celeb = goal_service.celebrate_if_complete(session, goal_id)
                page.pop_dialog()
                _offer_undo_snack(log, celeb or "Лог добавлен")
                reload()
                page.update()

            amount_field = ft.TextField(
                label="Сколько добавить?",
                value="1",
                keyboard_type=ft.KeyboardType.NUMBER,
                border_color="#2A2A32",
                focused_border_color=ORANGE,
                color=TEXT,
            )
            page.show_dialog(
                ft.AlertDialog(
                    title=ft.Text("Прогресс", color=TEXT),
                    content=amount_field,
                    actions=[
                        ft.TextButton("Отмена", on_click=lambda e: page.pop_dialog()),
                        ft.TextButton("Сохранить", on_click=submit),
                    ],
                )
            )

        def on_quick_fill(goal_id: int):
            celeb = None
            log = None
            with get_session() as session:
                qs = goal_service.today_quotas(session)
                item = next((q for q in qs if q["goal"].id == goal_id), None)
                if not item:
                    return
                rem_amt = max(0.0, float(item["quota"]) - float(item["today"]))
                amount = rem_amt if rem_amt > 0 else 1.0
                try:
                    payload = ProgressLogCreate(
                        goal_id=goal_id, amount=amount, note="Быстрый +квота"
                    )
                except ValidationError:
                    show_toast(page, "Не удалось заполнить квоту", kind="error")
                    return
                log = add_progress(session, payload)
                celeb = goal_service.celebrate_if_complete(session, goal_id)
            _offer_undo_snack(log, celeb or "Квота заполнена")
            reload()
            page.update()

        today_cards = [
            today_quota_card(
                q,
                on_tap=on_open_goal,
                on_quick_log=on_progress,
                on_quick_fill=on_quick_fill,
                streak=streak_map.get(q["goal"].id, 0),
                compact=compact,
            )
            for q in quotas
        ] or [
            empty_state(
                "Нет целей на сегодня",
                "Создайте первую цель — квоты появятся здесь",
                emoji="🎯",
                action_label="Создать",
                on_action=on_add,
            )
        ]
        today_section = ft.Column(
            [section_title("Сегодня · квоты")] + today_cards,
            spacing=10,
        )

        # Streak row
        streak_row = None
        if streaks:
            streak_row = ft.Column(
                [
                    section_title("Серии"),
                    ft.Row(
                        [
                            streak_badge_chip(s.title, s.current_streak, today_ok=s.today_complete)
                            for s in streaks[:3]
                        ],
                        spacing=8,
                    ),
                ],
                spacing=10,
            )

        def toggle_pin(tid: int, pinned: bool):
            with get_session() as session:
                task_service.set_pinned(session, tid, pinned)
            haptic(page, "light")
            reload()

        def cycle(tid: int):
            order = ["todo", "in_progress", "done"]
            with get_session() as session:
                t = task_service.get_task(session, tid)
                if not t:
                    return
                nxt = order[(order.index(t.status) + 1) % len(order)] if t.status in order else "todo"
                task_service.set_status(session, tid, nxt)
            haptic(page, "medium" if nxt == "done" else "selection")
            reload()
            page.update()

        def delete(tid: int):
            def yes():
                with get_session() as session:
                    task_service.delete_task(session, tid)
                reload()
                page.update()

            confirm_delete(
                page,
                title="Удалить задачу?",
                message="Задача будет удалена безвозвратно.",
                on_confirm=yes,
            )

        goal_cards = [
            goal_card(
                g,
                on_tap=on_open_goal,
                on_add_progress=on_progress,
                streak=streak_map.get(g.id, 0),
                compact=compact,
            )
            for g in goals[:3]
        ] or [
            empty_state(
                "Целей пока нет",
                "Добавьте цель с дневной квотой",
                emoji="🏁",
                action_label="Создать",
                on_action=on_add,
            )
        ]
        goal_section = ft.Column(
            [section_title("Цели")] + goal_cards,
            spacing=10,
        )

        task_cards = [
            task_card(
                t,
                on_tap=on_open_task,
                on_cycle_status=cycle,
                on_delete=delete,
                on_toggle_pin=toggle_pin,
                compact=compact,
            )
            for t in tasks
        ] or [
            empty_state(
                "Нет активных задач",
                "Все сделано — или создайте новую",
                emoji="✅",
                action_label="Новая задача",
                on_action=on_add,
            )
        ]
        task_section = ft.Column(
            [section_title("Задачи · сегодня")] + task_cards,
            spacing=8 if dense else 10,
        )

        timer_chip = None
        if active_timer:
            rem = active_timer.remaining_sec
            m, s = divmod(max(0, rem), 60)
            st = "Идёт" if active_timer.status == "running" else "Пауза"
            timer_chip = ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.TIMER, color=ORANGE, size=18),
                        ft.Text(
                            f"{active_timer.label}: {m:02d}:{s:02d} · {st}",
                            size=13,
                            color=TEXT,
                            expand=True,
                        ),
                        ft.Text("Открыть", size=12, color=ORANGE, weight=ft.FontWeight.W_600),
                    ],
                    spacing=8,
                ),
                padding=12,
                **card_style(),
                on_click=lambda e: on_open_focus() if on_open_focus else None,
                ink=True,
            )

        def do_snooze_all_overdue(_e=None):
            with get_session() as session:
                n = task_service.snooze_all_overdue(session, days=1)
            if n:
                show_toast(page, f"Отложено +1 день: {n}", kind="success")
            else:
                show_toast(page, "Нечего откладывать", kind="info")
            refresh_all()

        overdue_banner = None
        if overdue_tasks and not quiet:
            n = len(overdue_tasks)
            titles = ", ".join(t.title[:18] for t in overdue_tasks[:3])
            if n > 3:
                titles += "…"
            rem_rows = []
            for t in overdue_tasks[: (2 if dense else 4)]:
                rem_rows.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.EVENT_BUSY, color=RED, size=14),
                                ft.Text(
                                    t.title,
                                    size=12,
                                    color=TEXT,
                                    expand=True,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                                ft.Text(
                                    t.due_date.isoformat() if t.due_date else "",
                                    size=11,
                                    color=RED,
                                ),
                            ],
                            spacing=8,
                        ),
                        padding=ft.Padding.symmetric(horizontal=4, vertical=2),
                        on_click=(lambda e, tid=t.id: on_open_task(tid) if on_open_task else None),
                        ink=True,
                    )
                )
            overdue_banner = ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=RED, size=20),
                                ft.Column(
                                    [
                                        ft.Text(
                                            f"Есть просроченные ({n})",
                                            size=14,
                                            weight=ft.FontWeight.W_700,
                                            color=TEXT,
                                        ),
                                        ft.Text(
                                            "Напоминания · нажмите для перехода",
                                            size=11,
                                            color=MUTED,
                                        ),
                                    ],
                                    spacing=2,
                                    expand=True,
                                ),
                                ft.TextButton(
                                    "+1д",
                                    on_click=do_snooze_all_overdue,
                                    style=ft.ButtonStyle(color=ORANGE),
                                    tooltip="Отложить все просроченные на 1 день",
                                ),
                                ft.TextButton(
                                    "Все →",
                                    on_click=lambda e: on_open_overdue() if on_open_overdue else None,
                                    style=ft.ButtonStyle(color=RED),
                                ),
                            ],
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        *rem_rows,
                    ],
                    spacing=6,
                ),
                padding=14,
                bgcolor="#2A1212",
                border=ft.Border.all(1, RED),
                border_radius=ft.BorderRadius.all(14),
            )

        due_today_banner = None
        if due_today_tasks and not quiet:
            n = len(due_today_tasks)
            dt_rows = []
            for t in due_today_tasks[: (2 if dense else 4)]:
                dt_rows.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.TODAY_OUTLINED, color=ORANGE, size=14),
                                ft.Text(
                                    t.title,
                                    size=12,
                                    color=TEXT,
                                    expand=True,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                                ft.Text("сегодня", size=11, color=ORANGE, weight=ft.FontWeight.W_600),
                            ],
                            spacing=8,
                        ),
                        padding=ft.Padding.symmetric(horizontal=4, vertical=2),
                        on_click=(lambda e, tid=t.id: on_open_task(tid) if on_open_task else None),
                        ink=True,
                    )
                )
            due_today_banner = ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.EVENT_AVAILABLE_ROUNDED, color=ORANGE, size=20),
                                ft.Column(
                                    [
                                        ft.Text(
                                            f"На сегодня ({n})",
                                            size=14,
                                            weight=ft.FontWeight.W_700,
                                            color=TEXT,
                                        ),
                                        ft.Text(
                                            "Срок сегодня · нажмите для перехода",
                                            size=11,
                                            color=MUTED,
                                        ),
                                    ],
                                    spacing=2,
                                    expand=True,
                                ),
                                ft.TextButton(
                                    "Все →",
                                    on_click=lambda e: on_open_due_today() if on_open_due_today else None,
                                    style=ft.ButtonStyle(color=ORANGE),
                                ),
                            ],
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        *dt_rows,
                    ],
                    spacing=6,
                ),
                padding=14,
                bgcolor="#2A1C12",
                border=ft.Border.all(1, ORANGE),
                border_radius=ft.BorderRadius.all(14),
            )

        week_banner = None
        if week_sum["count"]:
            w_rows = []
            for t in week_sum["tasks"][:4]:
                label, kind = task_service.format_due_label(t)
                col = RED if kind == "overdue" else (ORANGE if kind in ("today", "soon") else MUTED)
                w_rows.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.DATE_RANGE, color=col, size=14),
                                ft.Text(
                                    t.title,
                                    size=12,
                                    color=TEXT,
                                    expand=True,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                                ft.Text(label, size=11, color=col, weight=ft.FontWeight.W_600),
                            ],
                            spacing=8,
                        ),
                        padding=ft.Padding.symmetric(horizontal=4, vertical=2),
                        on_click=(
                            lambda e, tid=t.id: on_open_task(tid) if on_open_task else None
                        ),
                        ink=True,
                    )
                )
            week_banner = ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.VIEW_WEEK_OUTLINED, color=ORANGE, size=20),
                                ft.Column(
                                    [
                                        ft.Text(
                                            f"На этой неделе ({week_sum['count']})",
                                            size=14,
                                            weight=ft.FontWeight.W_700,
                                            color=TEXT,
                                        ),
                                        ft.Text(
                                            f"{week_sum['start'].isoformat()} — {week_sum['end'].isoformat()}"
                                            + (
                                                f" · просрочено {week_sum['overdue']}"
                                                if week_sum["overdue"]
                                                else ""
                                            ),
                                            size=11,
                                            color=MUTED,
                                        ),
                                    ],
                                    spacing=2,
                                    expand=True,
                                ),
                            ],
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        *w_rows,
                    ],
                    spacing=6,
                ),
                padding=14,
                bgcolor="#1A1A22",
                border=ft.Border.all(1, BORDER),
                border_radius=ft.BorderRadius.all(14),
                animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
            )

        stuck_section = None
        if stuck:
            stuck_rows: list[ft.Control] = []
            for sg in stuck[:5]:
                idle_label = (
                    f"{sg.days_idle} дн без лога"
                    if sg.last_logged_at is not None
                    else f"{sg.days_idle} дн без лога"
                )
                stuck_rows.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.HOURGLASS_EMPTY, color=MUTED, size=16),
                                ft.Column(
                                    [
                                        ft.Text(
                                            sg.title,
                                            size=13,
                                            weight=ft.FontWeight.W_600,
                                            color=TEXT,
                                            max_lines=1,
                                            overflow=ft.TextOverflow.ELLIPSIS,
                                        ),
                                        ft.Text(
                                            f"{idle_label} · {sg.percent_complete:.0f}%",
                                            size=11,
                                            color=MUTED,
                                        ),
                                    ],
                                    spacing=2,
                                    expand=True,
                                ),
                            ],
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                        bgcolor="#1A1A22",
                        border=ft.Border.all(1, BORDER),
                        border_radius=ft.BorderRadius.all(12),
                        on_click=(
                            lambda e, gid=sg.goal_id: on_open_goal(gid)
                            if on_open_goal
                            else None
                        ),
                        ink=True,
                    )
                )
            stuck_section = ft.Column(
                [section_title("Застой")] + stuck_rows,
                spacing=8,
            )


        def show_daily_wrap(_e=None):
            with get_session() as session:
                wrap = analytics_service.daily_wrap(session)
            q_label = (
                f"{wrap.quotas_met}/{wrap.quotas_total}"
                if wrap.quotas_total
                else "—"
            )
            cards = [
                ("🎯", "Квоты закрыты", q_label, ORANGE),
                ("✅", "Задач готово", str(wrap.tasks_done), "#3DDC97"),
                ("⏱️", "Фокус, мин", str(wrap.focus_min), "#4C8DFF"),
            ]
            rows: list[ft.Control] = []
            for emoji, label, value, color in cards:
                rows.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Text(emoji, size=22),
                                ft.Column(
                                    [
                                        ft.Text(label, size=12, color=MUTED),
                                        ft.Text(
                                            value,
                                            size=20,
                                            weight=ft.FontWeight.W_700,
                                            color=color,
                                        ),
                                    ],
                                    spacing=2,
                                    expand=True,
                                ),
                            ],
                            spacing=12,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=ft.Padding.symmetric(horizontal=4, vertical=6),
                    )
                )
            tip_block = ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.LIGHTBULB_OUTLINE, color=ORANGE, size=16),
                                ft.Text(
                                    "Совет на завтра",
                                    size=12,
                                    weight=ft.FontWeight.W_600,
                                    color=ORANGE,
                                ),
                            ],
                            spacing=6,
                        ),
                        ft.Text(
                            wrap.tip_tomorrow or "Завтра тоже будет хороший день",
                            size=13,
                            color=TEXT,
                        ),
                    ],
                    spacing=6,
                ),
                padding=12,
                bgcolor="#1A1A22",
                border=ft.Border.all(1, BORDER),
                border_radius=ft.BorderRadius.all(12),
            )
            show_info(
                page,
                title="Итог дня",
                content=ft.Column(
                    [
                        muted(f"Сегодня · {wrap.day.isoformat()}"),
                        *rows,
                        tip_block,
                    ],
                    spacing=8,
                    tight=True,
                    scroll=ft.ScrollMode.AUTO,
                    width=320,
                ),
                ok_label="Закрыть",
            )

        def _digest_chip(label: str, icon, on_click, tooltip: str) -> ft.Control:
            return ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(icon, color=ORANGE, size=14),
                        ft.Text(
                            label,
                            size=12,
                            weight=ft.FontWeight.W_600,
                            color=TEXT,
                        ),
                    ],
                    spacing=6,
                    tight=True,
                ),
                padding=ft.Padding.symmetric(horizontal=10, vertical=7),
                bgcolor="#1C1C22",
                border=ft.Border.all(1, BORDER),
                border_radius=ft.BorderRadius.all(16),
                on_click=on_click,
                ink=True,
                tooltip=tooltip,
            )

        wrap_btn = _digest_chip(
            "Итог",
            ft.Icons.NIGHTLIGHT_ROUND,
            show_daily_wrap,
            "Сводка за сегодня",
        )

        def show_morning_briefing(_e=None):
            with get_session() as session:
                brief = analytics_service.morning_briefing(session)
            cards = [
                ("⚠️", "Просрочено", str(brief.overdue_count), RED),
                ("📅", "На сегодня", str(brief.due_today), "#4C8DFF"),
                ("⚡", "Импульс", str(brief.momentum.score), ORANGE),
            ]
            rows: list[ft.Control] = []
            for emoji, label, value, color in cards:
                rows.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Text(emoji, size=22),
                                ft.Column(
                                    [
                                        ft.Text(label, size=12, color=MUTED),
                                        ft.Text(
                                            value,
                                            size=20,
                                            weight=ft.FontWeight.W_700,
                                            color=color,
                                        ),
                                    ],
                                    spacing=2,
                                    expand=True,
                                ),
                            ],
                            spacing=12,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=ft.Padding.symmetric(horizontal=4, vertical=6),
                    )
                )
            quota_items: list[ft.Control] = [
                ft.Text(
                    "Открытые квоты",
                    size=12,
                    weight=ft.FontWeight.W_600,
                    color=ORANGE,
                )
            ]
            if brief.incomplete_quotas:
                for q in brief.incomplete_quotas[:8]:
                    quota_items.append(
                        ft.Text(
                            f"· {q.title} — {q.today:g}/{q.quota:g}",
                            size=13,
                            color=TEXT,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        )
                    )
            else:
                quota_items.append(
                    ft.Text("Все квоты закрыты", size=13, color=MUTED)
                )
            quota_block = ft.Container(
                content=ft.Column(quota_items, spacing=4),
                padding=12,
                bgcolor="#1A1A22",
                border=ft.Border.all(1, BORDER),
                border_radius=ft.BorderRadius.all(12),
            )
            sug = brief.suggestion
            sug_text = (sug.text if sug else "") or "Всё чисто — хороший старт дня."
            tip_block = ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.LIGHTBULB_OUTLINE, color=ORANGE, size=16),
                                ft.Text(
                                    "Совет",
                                    size=12,
                                    weight=ft.FontWeight.W_600,
                                    color=ORANGE,
                                ),
                            ],
                            spacing=6,
                        ),
                        ft.Text(sug_text, size=13, color=TEXT),
                    ],
                    spacing=6,
                ),
                padding=12,
                bgcolor="#1A1A22",
                border=ft.Border.all(1, BORDER),
                border_radius=ft.BorderRadius.all(12),
            )
            show_info(
                page,
                title="Брифинг",
                content=ft.Column(
                    [
                        muted(f"Утро · {brief.day.isoformat()}"),
                        *rows,
                        quota_block,
                        tip_block,
                    ],
                    spacing=8,
                    tight=True,
                    scroll=ft.ScrollMode.AUTO,
                    width=320,
                ),
                ok_label="Закрыть",
            )

        briefing_btn = _digest_chip(
            "Брифинг",
            ft.Icons.WB_SUNNY_OUTLINED,
            show_morning_briefing,
            "Утренний обзор",
        )
        momentum_chip.on_click = show_morning_briefing

        def show_tomorrow_plan(_e=None):
            with get_session() as session:
                plan = analytics_service.tomorrow_plan(session)
            due_items: list[ft.Control] = [
                ft.Text(
                    "На завтра",
                    size=12,
                    weight=ft.FontWeight.W_600,
                    color=ORANGE,
                )
            ]
            if plan.due_tomorrow:
                for it in plan.due_tomorrow[:10]:
                    est = f" · {it.estimated_min}м" if it.estimated_min else ""
                    due_items.append(
                        ft.Text(
                            f"· {it.title}{est}",
                            size=13,
                            color=TEXT,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        )
                    )
                if len(plan.due_tomorrow) > 10:
                    due_items.append(
                        ft.Text(
                            f"…и ещё {len(plan.due_tomorrow) - 10}",
                            size=12,
                            color=MUTED,
                        )
                    )
            else:
                due_items.append(
                    ft.Text("Нет задач со сроком на завтра", size=13, color=MUTED)
                )
            due_block = ft.Container(
                content=ft.Column(due_items, spacing=4),
                padding=12,
                bgcolor="#1A1A22",
                border=ft.Border.all(1, BORDER),
                border_radius=ft.BorderRadius.all(12),
            )
            open_items: list[ft.Control] = [
                ft.Text(
                    "Ещё открыто сегодня",
                    size=12,
                    weight=ft.FontWeight.W_600,
                    color="#4C8DFF",
                )
            ]
            if plan.open_today:
                for it in plan.open_today[:8]:
                    open_items.append(
                        ft.Text(
                            f"· {it.title}",
                            size=13,
                            color=TEXT,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        )
                    )
                if len(plan.open_today) > 8:
                    open_items.append(
                        ft.Text(
                            f"…и ещё {len(plan.open_today) - 8}",
                            size=12,
                            color=MUTED,
                        )
                    )
            else:
                open_items.append(
                    ft.Text("Сегодняшние сроки закрыты", size=13, color=MUTED)
                )
            open_block = ft.Container(
                content=ft.Column(open_items, spacing=4),
                padding=12,
                bgcolor="#1A1A22",
                border=ft.Border.all(1, BORDER),
                border_radius=ft.BorderRadius.all(12),
            )
            tip_block = ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.LIGHTBULB_OUTLINE, color=ORANGE, size=16),
                                ft.Text(
                                    "Подсказка",
                                    size=12,
                                    weight=ft.FontWeight.W_600,
                                    color=ORANGE,
                                ),
                            ],
                            spacing=6,
                        ),
                        ft.Text(plan.tip or "", size=13, color=TEXT),
                    ],
                    spacing=6,
                ),
                padding=12,
                bgcolor="#1A1A22",
                border=ft.Border.all(1, BORDER),
                border_radius=ft.BorderRadius.all(12),
            )
            show_info(
                page,
                title="План на завтра",
                content=ft.Column(
                    [
                        muted(f"Завтра · {plan.day.isoformat()}"),
                        due_block,
                        open_block,
                        tip_block,
                    ],
                    spacing=8,
                    tight=True,
                    scroll=ft.ScrollMode.AUTO,
                    width=320,
                ),
                ok_label="Закрыть",
            )

        tomorrow_btn = _digest_chip(
            "Завтра",
            ft.Icons.EVENT_OUTLINED,
            show_tomorrow_plan,
            "План на завтра",
        )

        brief_wrap_row = ft.Row(
            [briefing_btn, wrap_btn, tomorrow_btn],
            spacing=8,
            wrap=True,
            run_spacing=6,
        )

        # Wave AI: weekly goal progress (ISO week completed_at / target)
        week_pct = 0.0 if week_target <= 0 else min(1.0, week_done / week_target)
        week_goal_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(
                                f"Неделя: {week_done}/{week_target} задач",
                                size=13,
                                weight=ft.FontWeight.W_700,
                                color=TEXT,
                                expand=True,
                            ),
                            ft.Text(
                                f"{int(round(week_pct * 100))}%",
                                size=12,
                                weight=ft.FontWeight.W_600,
                                color=ORANGE if week_pct >= 1.0 else MUTED,
                            ),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.ProgressBar(
                        value=week_pct,
                        color=ORANGE,
                        bgcolor="#2A2A32",
                        bar_height=8,
                    ),
                ],
                spacing=8,
            ),
            padding=14,
            bgcolor="#1A1A22",
            border=ft.Border.all(1, ORANGE if week_pct >= 1.0 else BORDER),
            border_radius=ft.BorderRadius.all(14),
            tooltip="Цель недели · ISO пн–вс · completed_at",
        )

        # Wave AH: soft evening wind-down card (not a hard block)
        evening_card = None
        if wind_down:
            incomplete_n = sum(1 for q in quotas if not q.get("complete"))
            if incomplete_n:
                sub = f"Незакрытых квот: {incomplete_n} · откройте итог дня"
            else:
                sub = "Все квоты закрыты · можно подвести итог дня"
            evening_card = ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.NIGHTLIGHT_ROUND, color="#9B8CFF", size=20),
                        ft.Column(
                            [
                                ft.Text(
                                    "Вечерний режим",
                                    size=14,
                                    weight=ft.FontWeight.W_700,
                                    color=TEXT,
                                ),
                                ft.Text(
                                    sub,
                                    size=11,
                                    color=MUTED,
                                    max_lines=2,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        ft.Text(
                            "Итог →",
                            size=12,
                            weight=ft.FontWeight.W_700,
                            color="#9B8CFF",
                        ),
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=14,
                bgcolor="#1A1828",
                border=ft.Border.all(1, "#3A3560"),
                border_radius=ft.BorderRadius.all(14),
                on_click=show_daily_wrap,
                ink=True,
                tooltip="Мягкое напоминание · не блокирует работу",
            )

        # --- Wave X: quick capture ---
        capture_field = ft.TextField(
            hint_text="Быстрый захват…",
            border_color=BORDER,
            focused_border_color=ORANGE,
            color=TEXT,
            cursor_color=ORANGE,
            bgcolor="#1C1C22",
            border_radius=12,
            dense=True,
            text_size=14,
            expand=True,
            content_padding=ft.Padding.symmetric(horizontal=12, vertical=10),
        )

        def do_quick_capture(_e=None):
            raw = (capture_field.value or "").strip()
            if not raw:
                validation_fail(page, "Введите название", capture_field)
                return
            try:
                with get_session() as session:
                    task_service.quick_capture(session, raw)
            except Exception as exc:
                show_toast(page, str(exc), kind="error")
                return
            capture_field.value = ""
            show_toast(page, "В inbox", kind="success")
            reload()
            refresh_all()

        capture_row = ft.Container(
            content=ft.Row(
                [
                    capture_field,
                    ft.Container(
                        content=ft.Icon(ft.Icons.ADD, color="#0F0F12", size=20),
                        bgcolor=ORANGE,
                        padding=10,
                        border_radius=ft.BorderRadius.all(12),
                        on_click=do_quick_capture,
                        ink=True,
                        tooltip="В inbox",
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=4, vertical=2),
        )

        # --- Wave X: daily note ---
        note_field = ft.TextField(
            value=daily_note or "",
            hint_text="Заметка дня…",
            multiline=True,
            min_lines=2,
            max_lines=4,
            border_color=BORDER,
            focused_border_color=ORANGE,
            color=TEXT,
            cursor_color=ORANGE,
            bgcolor="#1C1C22",
            border_radius=12,
            text_size=13,
            content_padding=12,
        )

        def save_daily_note(_e=None):
            text = note_field.value or ""
            with get_session() as session:
                settings_service.set_daily_note(session, text)
            show_toast(page, "Заметка сохранена", kind="success")
            page.update()

        daily_note_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.EDIT_NOTE, color=ORANGE, size=18),
                            ft.Text(
                                "Заметка дня",
                                size=14,
                                weight=ft.FontWeight.W_700,
                                color=TEXT,
                                expand=True,
                            ),
                            ft.Container(
                                content=ft.Text(
                                    "Сохранить",
                                    size=12,
                                    weight=ft.FontWeight.W_700,
                                    color="#0F0F12",
                                ),
                                bgcolor=ORANGE,
                                padding=ft.Padding.symmetric(horizontal=12, vertical=6),
                                border_radius=ft.BorderRadius.all(10),
                                on_click=save_daily_note,
                                ink=True,
                            ),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    note_field,
                ],
                spacing=8,
            ),
            padding=14,
            bgcolor="#1A1A22",
            border=ft.Border.all(1, BORDER),
            border_radius=ft.BorderRadius.all(14),
        )

        # --- Wave X: undo last complete ---
        undo_chip = None
        if last_done_id is not None:
            def do_undo_complete(_e=None, _tid=last_done_id):
                with get_session() as session:
                    restored = task_service.undo_last_complete(session)
                if restored:
                    show_toast(page, f"↩ Отменено: {restored.title}", kind="success")
                else:
                    show_toast(page, "Нечего отменять", kind="error")
                reload()
                refresh_all()

            undo_chip = ft.Container(
                content=ft.Row(
                    [
                        ft.Text(
                            "↩ Отменить Готово",
                            size=12,
                            weight=ft.FontWeight.W_700,
                            color=ORANGE,
                        ),
                        ft.Text(
                            (last_done_title or "")[:28],
                            size=11,
                            color=MUTED,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            expand=True,
                        ),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                bgcolor="#2A1C12",
                border=ft.Border.all(1, ORANGE),
                border_radius=ft.BorderRadius.all(12),
                on_click=do_undo_complete,
                ink=True,
                tooltip="Вернуть последнюю завершённую задачу",
            )

        # Banner cap: at most MAX_HOME_BANNERS on Home; rest → «ещё» / Reminders.
        banner_candidates: list[ft.Control] = []
        if overdue_banner:
            banner_candidates.append(overdue_banner)
        if evening_card:
            banner_candidates.append(evening_card)
        if smart_card:
            banner_candidates.append(smart_card)
        if backup_tip:
            banner_candidates.append(backup_tip)
        shown_banners = banner_candidates[:MAX_HOME_BANNERS]
        hidden_banner_n = max(0, len(banner_candidates) - MAX_HOME_BANNERS)
        more_chip = None
        if hidden_banner_n:
            more_chip = _digest_chip(
                f"ещё {hidden_banner_n}",
                ft.Icons.MORE_HORIZ,
                lambda e: on_open_reminders() if on_open_reminders else None,
                "Остальные напоминания",
            )

        sheet_open = bool(today_sheet_open["value"])
        today_toggle = ft.Container(
            content=ft.Row(
                [
                    ft.Text(
                        "Сегодня",
                        size=14,
                        weight=ft.FontWeight.W_700,
                        color=TEXT,
                    ),
                    ft.Text(
                        "свернуть" if sheet_open else "квоты · цели · заметка",
                        size=11,
                        color=MUTED,
                        expand=True,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Icon(
                        ft.Icons.EXPAND_LESS if sheet_open else ft.Icons.EXPAND_MORE,
                        color=MUTED,
                        size=20,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            bgcolor="#1A1A22",
            border=ft.Border.all(1, BORDER),
            border_radius=ft.BorderRadius.all(14),
            on_click=toggle_today_sheet,
            ink=True,
            tooltip="Квоты, цели, заметка дня",
        )

        digest_row_controls: list[ft.Control] = [briefing_btn, wrap_btn, tomorrow_btn]
        if more_chip:
            digest_row_controls.append(more_chip)
        if on_open_note:
            digest_row_controls.append(
                _digest_chip(
                    "Заметка",
                    ft.Icons.DESCRIPTION_OUTLINED,
                    lambda e: on_open_note("home.md", "Дом"),
                    "home.md",
                )
            )
        if on_open_focus:
            digest_row_controls.append(
                _digest_chip(
                    "Фокус",
                    ft.Icons.TIMER_OUTLINED,
                    lambda e: on_open_focus(),
                    "Таймер фокуса",
                )
            )
        brief_wrap_row = ft.Row(
            digest_row_controls,
            spacing=8,
            wrap=True,
            run_spacing=6,
        )

        controls: list[ft.Control] = [header]
        controls.append(capture_row)
        if undo_chip:
            controls.append(undo_chip)
        if timer_chip:
            controls.append(timer_chip)
        controls.extend(shown_banners)
        controls.append(task_section)
        controls.append(brief_wrap_row)
        controls.append(today_toggle)
        if sheet_open:
            controls.append(tip_line)
            controls.append(week_goal_card)
            if due_today_banner:
                controls.append(due_today_banner)
            if week_banner:
                controls.append(week_banner)
            controls.append(today_section)
            if streak_row:
                controls.append(streak_row)
            if stuck_section:
                controls.append(stuck_section)
            controls.append(goal_section)
            controls.append(daily_note_card)
        controls.append(ft.Container(height=8))
        body.controls.extend(controls)
        try:
            root.padding = screen_insets(compact=dense)
        except NameError:
            pass
        page.update()

    root = ft.Container(
        content=body,
        padding=screen_insets(),
        expand=True,
    )

    reload()
    maybe_show_onboarding(page)
    return root
