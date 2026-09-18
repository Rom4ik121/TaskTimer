"""Goal detail — progress ring, daily quota, ProgressLog CRUD, edit fields."""
from __future__ import annotations

import flet as ft
from pydantic import ValidationError

from app.db import get_session
from app.schemas import GoalUpdate, ProgressLogCreate, ProgressLogUpdate
from app.services import goal_service, streak_service
from app.ui.components.cards import empty_state
from app.ui.components.dialogs import confirm_delete, show_snack
from app.ui.haptics import haptic
from app.ui.components.progress_ring import donut_progress
from app.ui.theme import BORDER, GREEN, MUTED, ORANGE, RED, TEXT, card_style, markdown_lite, muted, section_title


def build_goal_detail(
    page: ft.Page, goal_id: int, *, on_back, refresh_all
) -> ft.Control:
    body = ft.Column(spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)

    def reload(_: ft.ControlEvent | None = None):
        body.controls.clear()
        with get_session() as session:
            goal = goal_service.get_goal(session, goal_id)
            if not goal:
                body.controls.append(ft.Text("Цель не найдена", color=TEXT))
                body.controls.append(ft.TextButton("Назад", on_click=lambda e: on_back()))
                page.update()
                return
            logs = goal_service.list_logs(session, goal_id)
            today = goal_service.today_logged(session, goal_id)
            streak_info = streak_service.goal_streak(session, goal)
            cal_days = streak_service.quota_calendar(session, goal, days=28)
            g_title = goal.title
            g_desc = goal.description or ""
            g_target = goal.target_value
            g_unit = goal.unit
            g_quota = goal.daily_quota
            g_current = goal.current_value
            g_pct = goal.percent_complete
            g_archived = bool(getattr(goal, "archived", False))
            g_eta = goal_service.days_to_complete(goal)
            log_rows = [
                {
                    "id": lg.id,
                    "amount": lg.amount,
                    "note": lg.note or "",
                    "logged_at": lg.logged_at,
                }
                for lg in logs
            ]

        complete = today >= g_quota

        title_f = ft.TextField(
            label="Название",
            value=g_title,
            border_color=BORDER,
            focused_border_color=ORANGE,
            color=TEXT,
        )
        desc_f = ft.TextField(
            label="Описание / заметки",
            value=g_desc,
            multiline=True,
            min_lines=3,
            max_lines=8,
            border_color=BORDER,
            focused_border_color=ORANGE,
            color=TEXT,
            hint_text="Поддерживается **жирный**",
        )
        desc_preview = ft.Container(
            content=ft.Column(
                [
                    muted("Превью"),
                    markdown_lite(g_desc, muted_if_empty="Нет заметок"),
                ],
                spacing=4,
            ),
            padding=ft.Padding.symmetric(horizontal=4, vertical=2),
        )

        def _refresh_gpreview(_=None):
            desc_preview.content.controls[1] = markdown_lite(
                desc_f.value or "",
                muted_if_empty="Нет заметок",
            )
            page.update()

        desc_f.on_change = _refresh_gpreview
        target_f = ft.TextField(
            label="Цель (число)",
            value=str(g_target),
            border_color=BORDER,
            focused_border_color=ORANGE,
            color=TEXT,
        )
        unit_f = ft.TextField(
            label="Единица",
            value=g_unit,
            border_color=BORDER,
            focused_border_color=ORANGE,
            color=TEXT,
        )
        quota_f = ft.TextField(
            label="Дневная квота",
            value=str(g_quota),
            border_color=BORDER,
            focused_border_color=ORANGE,
            color=TEXT,
        )

        def save_goal(_):
            try:
                data = GoalUpdate(
                    title=title_f.value or "",
                    description=desc_f.value or "",
                    target_value=float((target_f.value or "0").replace(",", ".")),
                    unit=unit_f.value or "units",
                    daily_quota=float((quota_f.value or "1").replace(",", ".")),
                )
            except (ValidationError, ValueError) as exc:
                show_snack(page, str(exc), error=True)
                return
            with get_session() as session:
                goal_service.update_goal(session, goal_id, data)
            haptic(page, "success")
            show_snack(page, "Цель сохранена")
            refresh_all()
            reload()

        def do_delete_goal():
            with get_session() as session:
                goal_service.delete_goal(session, goal_id)
            show_snack(page, "Цель удалена")
            refresh_all()
            on_back()

        def ask_delete(_):
            confirm_delete(
                page,
                title="Удалить цель?",
                message=f"«{g_title}» и все логи будут удалены.",
                on_confirm=do_delete_goal,
            )

        def do_archive(_):
            with get_session() as session:
                if g_archived:
                    goal_service.unarchive_goal(session, goal_id)
                    show_snack(page, "Цель восстановлена")
                else:
                    goal_service.archive_goal(session, goal_id)
                    show_snack(page, "Цель в архиве")
            refresh_all()
            on_back()

        def add_log_dialog(_=None):
            amount = ft.TextField(
                label="Сколько",
                value=str(g_quota),
                keyboard_type=ft.KeyboardType.NUMBER,
                border_color=BORDER,
                focused_border_color=ORANGE,
                color=TEXT,
            )
            note = ft.TextField(
                label="Заметка",
                border_color=BORDER,
                focused_border_color=ORANGE,
                color=TEXT,
            )

            def submit(_):
                try:
                    data = ProgressLogCreate(
                        goal_id=goal_id,
                        amount=float((amount.value or "0").replace(",", ".")),
                        note=note.value or "",
                    )
                except (ValidationError, ValueError) as exc:
                    show_snack(page, str(exc), error=True)
                    return
                with get_session() as session:
                    goal_service.add_progress(session, data)
                    celeb = goal_service.celebrate_if_complete(session, goal_id)
                page.pop_dialog()
                show_snack(page, celeb or "Лог добавлен")
                refresh_all()
                reload()

            page.show_dialog(
                ft.AlertDialog(
                    title=ft.Text("Новый лог", color=TEXT),
                    content=ft.Column([amount, note], tight=True, spacing=10, height=140),
                    actions=[
                        ft.TextButton("Отмена", on_click=lambda e: page.pop_dialog()),
                        ft.TextButton("Сохранить", on_click=submit),
                    ],
                )
            )

        def edit_log(log_id: int, amount0: float, note0: str):
            amount = ft.TextField(
                label="Сколько",
                value=str(amount0),
                keyboard_type=ft.KeyboardType.NUMBER,
                border_color=BORDER,
                focused_border_color=ORANGE,
                color=TEXT,
            )
            note = ft.TextField(
                label="Заметка",
                value=note0,
                border_color=BORDER,
                focused_border_color=ORANGE,
                color=TEXT,
            )

            def submit(_):
                try:
                    data = ProgressLogUpdate(
                        amount=float((amount.value or "0").replace(",", ".")),
                        note=note.value or "",
                    )
                except (ValidationError, ValueError) as exc:
                    show_snack(page, str(exc), error=True)
                    return
                with get_session() as session:
                    goal_service.update_log(session, log_id, data)
                    celeb = goal_service.celebrate_if_complete(session, goal_id)
                page.pop_dialog()
                show_snack(page, celeb or "Лог обновлён")
                refresh_all()
                reload()

            page.show_dialog(
                ft.AlertDialog(
                    title=ft.Text("Редактировать лог", color=TEXT),
                    content=ft.Column([amount, note], tight=True, spacing=10, height=140),
                    actions=[
                        ft.TextButton("Отмена", on_click=lambda e: page.pop_dialog()),
                        ft.TextButton("Сохранить", on_click=submit),
                    ],
                )
            )

        def delete_log(log_id: int):
            def yes():
                with get_session() as session:
                    goal_service.delete_log(session, log_id)
                show_snack(page, "Лог удалён")
                refresh_all()
                reload()

            confirm_delete(
                page,
                title="Удалить лог?",
                message="Запись прогресса будет удалена.",
                on_confirm=yes,
            )

        log_controls = []
        for lg in log_rows:
            when = (
                lg["logged_at"].strftime("%d.%m.%Y %H:%M") if lg["logged_at"] else "—"
            )
            log_controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        f"+{lg['amount']:g} {g_unit}",
                                        size=13,
                                        weight=ft.FontWeight.W_600,
                                        color=TEXT,
                                    ),
                                    ft.Text(
                                        f"{when} · {lg['note'] or 'без заметки'}",
                                        size=11,
                                        color=MUTED,
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.EDIT_OUTLINED,
                                icon_size=16,
                                icon_color=MUTED,
                                on_click=lambda e, i=lg["id"], a=lg["amount"], n=lg["note"]: edit_log(
                                    i, a, n
                                ),
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE,
                                icon_size=16,
                                icon_color=RED,
                                on_click=lambda e, i=lg["id"]: delete_log(i),
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=12,
                    **card_style(),
                )
            )

        header = ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK_IOS_NEW,
                    icon_color=TEXT,
                    icon_size=18,
                    on_click=lambda e: on_back(),
                ),
                ft.Text("Цель", size=22, weight=ft.FontWeight.W_700, color=TEXT, expand=True),
                ft.IconButton(
                    icon=ft.Icons.UNARCHIVE_OUTLINED if g_archived else ft.Icons.ARCHIVE_OUTLINED,
                    icon_color=MUTED,
                    tooltip="Из архива" if g_archived else "В архив",
                    on_click=do_archive,
                ),
                ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=RED, on_click=ask_delete),
            ]
        )
        arch_hint = (
            muted("В архиве — скрыта с Дома и квот") if g_archived else None
        )

        hero = ft.Container(
            content=ft.Row(
                [
                    donut_progress(g_pct, size=110, thickness=14, subtitle=g_unit),
                    ft.Column(
                        [
                            ft.Text(g_title, size=18, weight=ft.FontWeight.W_700, color=TEXT),
                            ft.Text(
                                f"{g_current:g} / {g_target:g} {g_unit}",
                                size=13,
                                color=MUTED,
                            ),
                            ft.Text(
                                f"Сегодня: {today:g} / {g_quota:g}",
                                size=13,
                                color=GREEN if complete else ORANGE,
                                weight=ft.FontWeight.W_600,
                            ),
                            muted("квота выполнена" if complete else "квота не закрыта"),
                            ft.Text(
                                "Цель достигнута 🎉"
                                if g_eta == 0
                                else (
                                    f"Прогноз: ~{g_eta} дн. при квоте {g_quota:g}/день"
                                    if g_eta is not None
                                    else "Прогноз: задайте дневную квоту"
                                ),
                                size=12,
                                color=GREEN if g_eta == 0 else ORANGE,
                                weight=ft.FontWeight.W_600,
                            ),
                        ],
                        spacing=4,
                        expand=True,
                    ),
                ],
                spacing=14,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=16,
            **card_style(accent=True),
        )

        edit_block = ft.Container(
            content=ft.Column(
                [
                    section_title("Параметры"),
                    title_f,
                    desc_f,
                    desc_preview,
                    target_f,
                    unit_f,
                    quota_f,
                    ft.Container(
                        content=ft.Text(
                            "Сохранить цель",
                            size=14,
                            weight=ft.FontWeight.W_700,
                            color="#0F0F12",
                        ),
                        bgcolor=ORANGE,
                        padding=12,
                        border_radius=ft.BorderRadius.all(12),
                        alignment=ft.Alignment.CENTER,
                        on_click=save_goal,
                        ink=True,
                    ),
                ],
                spacing=10,
            ),
            padding=16,
            **card_style(),
        )

        history = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(
                            "История логов",
                            size=16,
                            weight=ft.FontWeight.W_600,
                            color=TEXT,
                            expand=True,
                        ),
                        ft.Container(
                            content=ft.Icon(ft.Icons.ADD_ROUNDED, size=18, color="#0F0F12"),
                            bgcolor=ORANGE,
                            width=36,
                            height=36,
                            border_radius=ft.BorderRadius.all(10),
                            alignment=ft.Alignment.CENTER,
                            on_click=add_log_dialog,
                            ink=True,
                        ),
                    ]
                ),
                *(log_controls or [empty_state("Логов пока нет", "Добавьте прогресс кнопкой +", emoji="📝")]),
            ],
            spacing=8,
        )


        # Streak calendar (4 weeks)
        cal_cells = []
        for item in cal_days:
            d = item["day"]
            met = item["met"]
            is_today = item["is_today"]
            bg = GREEN if met else ("#2A2A32" if not is_today else "#3D2200")
            cal_cells.append(
                ft.Container(
                    width=36,
                    height=36,
                    bgcolor=bg if met else "#1C1C22",
                    border=ft.Border.all(1, ORANGE if is_today else BORDER),
                    border_radius=ft.BorderRadius.all(8),
                    alignment=ft.Alignment.CENTER,
                    tooltip=f"{d.isoformat()}: {item['amount']:g}" + (" ✓" if met else ""),
                    content=ft.Text(
                        str(d.day),
                        size=11,
                        weight=ft.FontWeight.W_600 if met or is_today else None,
                        color=TEXT if met or is_today else MUTED,
                    ),
                )
            )
        # 7-col rows
        cal_rows = []
        # pad first week to weekday
        if cal_days:
            pad = cal_days[0]["day"].weekday()  # Mon=0
            pad_cells = [ft.Container(width=36, height=36) for _ in range(pad)]
            all_cells = pad_cells + cal_cells
        else:
            all_cells = cal_cells
        row = []
        for i, c in enumerate(all_cells):
            row.append(c)
            if len(row) == 7:
                cal_rows.append(ft.Row(row, spacing=4))
                row = []
        if row:
            while len(row) < 7:
                row.append(ft.Container(width=36, height=36))
            cal_rows.append(ft.Row(row, spacing=4))

        streak_block = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(
                                "Календарь квоты",
                                size=15,
                                weight=ft.FontWeight.W_700,
                                color=TEXT,
                                expand=True,
                            ),
                            ft.Text(
                                f"🔥 {streak_info.current_streak} · лучшая {streak_info.best_streak}",
                                size=12,
                                color=ORANGE,
                                weight=ft.FontWeight.W_600,
                            ),
                        ]
                    ),
                    muted("Дни с выполненной дневной квотой"),
                    ft.Row(
                        [
                            ft.Text(d, size=10, color=MUTED, width=36, text_align=ft.TextAlign.CENTER)
                            for d in ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
                        ],
                        spacing=4,
                    ),
                    *cal_rows,
                ],
                spacing=8,
            ),
            padding=16,
            **card_style(),
        )

        body.controls.extend(
            [header]
            + ([arch_hint] if arch_hint else [])
            + [hero, streak_block, edit_block, history, ft.Container(height=12)]
        )
        page.update()

    reload()
    return ft.Container(
        content=body,
        padding=ft.Padding.only(left=16, right=16, top=18, bottom=8),
        expand=True,
    )
