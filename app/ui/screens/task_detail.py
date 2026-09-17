"""Task detail — view / edit all fields, checklist, delete with confirm."""
from __future__ import annotations

from datetime import date

import flet as ft
from pydantic import ValidationError

from app.db import get_session
from app.schemas import SubtaskCreate, SubtaskUpdate, TaskUpdate
from app.services import goal_service, subtask_service, task_service
from app.ui.components.dialogs import confirm_delete, pick_date, show_snack
from app.ui.components.cards import empty_illus
from app.ui.theme import BORDER, GREEN, MUTED, ORANGE, RED, TEXT, card_style, markdown_lite, muted


def build_task_detail(
    page: ft.Page, task_id: int, *, on_back, refresh_all, on_open_task=None
) -> ft.Control:
    with get_session() as session:
        task = task_service.get_task(session, task_id)
        goals = goal_service.list_goals(session)
        subs = subtask_service.list_subtasks(session, task_id) if task else []
    if not task:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text("Задача не найдена", color=TEXT),
                    ft.TextButton("Назад", on_click=lambda e: on_back()),
                ]
            ),
            padding=16,
            expand=True,
        )

    title = ft.TextField(
        label="Название",
        value=task.title,
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
    )
    description = ft.TextField(
        label="Описание / заметки",
        value=task.description or "",
        multiline=True,
        min_lines=3,
        max_lines=10,
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
        hint_text="Поддерживается **жирный**",
    )
    notes_preview = ft.Container(
        content=ft.Column(
            [
                muted("Превью"),
                markdown_lite(
                    task.description or "",
                    muted_if_empty="Нет заметок",
                ),
            ],
            spacing=4,
        ),
        padding=ft.Padding.symmetric(horizontal=4, vertical=2),
    )

    def _refresh_preview(_=None):
        notes_preview.content.controls[1] = markdown_lite(
            description.value or "",
            muted_if_empty="Нет заметок",
        )
        page.update()

    description.on_change = _refresh_preview
    status_dd = ft.Dropdown(
        label="Статус",
        value=task.status,
        options=[
            ft.dropdown.Option("todo", "К выполнению"),
            ft.dropdown.Option("in_progress", "В работе"),
            ft.dropdown.Option("done", "Готово"),
        ],
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
    )
    priority_dd = ft.Dropdown(
        label="Приоритет",
        value=task.priority,
        options=[
            ft.dropdown.Option("low", "Низкий"),
            ft.dropdown.Option("medium", "Средний"),
            ft.dropdown.Option("high", "Высокий"),
        ],
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
    )
    goal_opts = [ft.dropdown.Option("", "Без цели")] + [
        ft.dropdown.Option(str(g.id), g.title) for g in goals
    ]
    goal_dd = ft.Dropdown(
        label="Цель",
        value=str(task.goal_id) if task.goal_id else "",
        options=goal_opts,
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
    )
    color_dd = ft.Dropdown(
        label="Метка",
        value=task.color_tag or "нет",
        options=[
            ft.dropdown.Option("нет", "Нет"),
            ft.dropdown.Option("оранжевый", "Оранжевый"),
            ft.dropdown.Option("синий", "Синий"),
            ft.dropdown.Option("зелёный", "Зелёный"),
            ft.dropdown.Option("красный", "Красный"),
            ft.dropdown.Option("фиолетовый", "Фиолетовый"),
        ],
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
    )
    recur_dd = ft.Dropdown(
        label="Повтор",
        value=getattr(task, "recur_rule", None) or "none",
        options=[
            ft.dropdown.Option("none", "Нет"),
            ft.dropdown.Option("daily", "Ежедневно"),
            ft.dropdown.Option("weekly", "Еженедельно"),
        ],
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
    )

    em0 = getattr(task, "estimated_min", None)
    estimate_field = ft.TextField(
        label="Оценка, мин",
        value="" if em0 is None else str(em0),
        keyboard_type=ft.KeyboardType.NUMBER,
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
        hint_text="например 25",
    )
    due_state = {"value": task.due_date}
    archived_state = {"value": bool(getattr(task, "archived", False))}
    pinned_state = {"value": bool(getattr(task, "pinned", False))}
    overdue = (
        task.status != "done"
        and not archived_state["value"]
        and task.due_date is not None
        and task.due_date < date.today()
    )
    due_label = ft.Text(
        task.due_date.isoformat() if task.due_date else "Не выбран",
        size=14,
        color=RED if overdue else TEXT,
        weight=ft.FontWeight.W_600 if overdue else None,
    )
    completed_info = ft.Text(
        f"Завершено: {task.completed_at.strftime('%Y-%m-%d %H:%M')}"
        if task.completed_at
        else "Ещё не завершена",
        size=12,
        color=MUTED,
    )
    archived_hint = ft.Text(
        "В архиве — скрыта из обычных списков" if archived_state["value"] else "",
        size=12,
        color=MUTED,
    )
    err = ft.Text("", color=RED, size=12)

    checklist_col = ft.Column(spacing=6)
    new_sub_field = ft.TextField(
        hint_text="Новый пункт…",
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
        expand=True,
        height=44,
    )

    def set_due(d: date | None):
        due_state["value"] = d
        is_od = (
            status_dd.value != "done"
            and d is not None
            and d < date.today()
        )
        due_label.value = d.isoformat() if d else "Не выбран"
        due_label.color = RED if is_od else TEXT
        page.update()

    def open_picker(_):
        pick_date(page, value=due_state["value"], on_picked=set_due)

    def clear_due(_):
        set_due(None)

    def do_snooze(days: int):
        with get_session() as session:
            updated = task_service.snooze_due(session, task_id, days=days)
        if not updated:
            show_snack(page, "Не удалось отложить", error=True)
            return
        set_due(updated.due_date)
        show_snack(page, f"Срок +{days} дн → {updated.due_date.isoformat()}")
        refresh_all()

    def reload_checklist():
        checklist_col.controls.clear()
        with get_session() as session:
            items = subtask_service.list_subtasks(session, task_id)
        if not items:
            checklist_col.controls.append(
                empty_illus("Пока пусто — добавьте пункты", emoji="☑️")
            )
        else:
            done_n = sum(1 for s in items if s.done)
            checklist_col.controls.append(
                ft.Text(
                    f"{done_n}/{len(items)} выполнено",
                    size=11,
                    color=GREEN if done_n == len(items) else MUTED,
                )
            )
            for i, s in enumerate(items):
                checklist_col.controls.append(_sub_row(s, index=i, total=len(items)))
        page.update()

    def _sub_row(s, *, index: int, total: int) -> ft.Control:
        def toggle(_):
            with get_session() as session:
                subtask_service.toggle_subtask(session, s.id)
            reload_checklist()

        def remove(_):
            def yes():
                with get_session() as session:
                    subtask_service.delete_subtask(session, s.id)
                reload_checklist()

            confirm_delete(
                page,
                title="Удалить подзадачу?",
                message="Пункт чек-листа будет удалён.",
                on_confirm=yes,
            )

        def move_up(_):
            with get_session() as session:
                subtask_service.move_subtask(session, s.id, -1)
            reload_checklist()

        def move_down(_):
            with get_session() as session:
                subtask_service.move_subtask(session, s.id, 1)
            reload_checklist()

        return ft.Container(
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.IconButton(
                                icon=ft.Icons.KEYBOARD_ARROW_UP,
                                icon_size=16,
                                icon_color=MUTED if index == 0 else TEXT,
                                on_click=move_up,
                                disabled=index == 0,
                                style=ft.ButtonStyle(padding=0),
                            ),
                            ft.IconButton(
                                icon=ft.Icons.KEYBOARD_ARROW_DOWN,
                                icon_size=16,
                                icon_color=MUTED if index >= total - 1 else TEXT,
                                on_click=move_down,
                                disabled=index >= total - 1,
                                style=ft.ButtonStyle(padding=0),
                            ),
                        ],
                        spacing=0,
                        tight=True,
                    ),
                    ft.Checkbox(
                        value=s.done,
                        fill_color=ORANGE,
                        on_change=toggle,
                    ),
                    ft.Text(
                        s.title,
                        size=13,
                        color=MUTED if s.done else TEXT,
                        style=ft.TextStyle(
                            decoration=ft.TextDecoration.LINE_THROUGH if s.done else None
                        ),
                        expand=True,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE,
                        icon_size=16,
                        icon_color=MUTED,
                        on_click=remove,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=2,
            ),
            bgcolor="#1C1C22",
            border_radius=ft.BorderRadius.all(10),
            padding=ft.Padding.symmetric(horizontal=4, vertical=2),
        )

    def add_sub(_):
        raw = (new_sub_field.value or "").strip()
        if not raw:
            show_snack(page, "Введите название пункта", error=True)
            return
        try:
            data = SubtaskCreate(task_id=task_id, title=raw)
        except ValidationError as exc:
            show_snack(page, str(exc), error=True)
            return
        with get_session() as session:
            created = subtask_service.create_subtask(session, data)
        if not created:
            show_snack(page, "Не удалось добавить", error=True)
            return
        new_sub_field.value = ""
        reload_checklist()
        show_snack(page, "Пункт добавлен")

    def save(_):
        err.value = ""
        try:
            gid = goal_dd.value
            tag = color_dd.value
            em_raw = (estimate_field.value or "").strip()
            em_val = int(em_raw) if em_raw else None
            data = TaskUpdate(
                title=title.value or "",
                description=description.value or "",
                status=status_dd.value,  # type: ignore[arg-type]
                priority=priority_dd.value,  # type: ignore[arg-type]
                due_date=due_state["value"],
                goal_id=int(gid) if gid else None,
                color_tag=None if not tag or tag == "нет" else tag,
                recur_rule=recur_dd.value or "none",  # type: ignore[arg-type]
                recur_anchor=due_state["value"],
                estimated_min=em_val,
            )
            with get_session() as session:
                updated = task_service.update_task(session, task_id, data)
                if updated:
                    completed_info.value = (
                        f"Завершено: {updated.completed_at.strftime('%Y-%m-%d %H:%M')}"
                        if updated.completed_at
                        else "Ещё не завершена"
                    )
                    od = (
                        updated.status != "done"
                        and updated.due_date is not None
                        and updated.due_date < date.today()
                    )
                    due_label.color = RED if od else TEXT
        except (ValidationError, ValueError) as exc:
            err.value = str(exc)
            page.update()
            return
        show_snack(page, "Сохранено")
        refresh_all()
        page.update()

    def do_delete():
        with get_session() as session:
            task_service.delete_task(session, task_id)
        show_snack(page, "Удалено")
        refresh_all()
        on_back()

    def do_toggle_pin(_):
        new_val = not pinned_state["value"]
        with get_session() as session:
            task_service.set_pinned(session, task_id, new_val)
        pinned_state["value"] = new_val
        pin_btn.icon = ft.Icons.PUSH_PIN if new_val else ft.Icons.PUSH_PIN_OUTLINED
        pin_btn.icon_color = ORANGE if new_val else MUTED
        pin_btn.tooltip = "Открепить" if new_val else "Закрепить"
        show_snack(page, "Закреплено" if new_val else "Откреплено")
        refresh_all()
        page.update()

    def do_duplicate(_):
        with get_session() as session:
            clone = task_service.duplicate_task(session, task_id)
        if not clone:
            show_snack(page, "Не удалось дублировать", error=True)
            return
        show_snack(page, "Дублировано")
        refresh_all()
        if on_open_task:
            on_open_task(clone.id)
        else:
            page.update()

    def do_archive(_):
        with get_session() as session:
            if archived_state["value"]:
                task_service.unarchive_task(session, task_id)
                archived_state["value"] = False
                show_snack(page, "Восстановлено из архива")
            else:
                task_service.archive_task(session, task_id)
                archived_state["value"] = True
                show_snack(page, "В архиве")
        refresh_all()
        on_back()

    def ask_delete(_):
        confirm_delete(
            page,
            title="Удалить задачу?",
            message=f'«{task.title}» и чек-лист будут удалены безвозвратно.',
            on_confirm=do_delete,
        )

    # Initial checklist populate
    if not subs:
        checklist_col.controls.append(empty_illus("Пока пусто — добавьте пункты", emoji="☑️"))
    else:
        done_n = sum(1 for s in subs if s.done)
        checklist_col.controls.append(
            ft.Text(
                f"{done_n}/{len(subs)} выполнено",
                size=11,
                color=GREEN if done_n == len(subs) else MUTED,
            )
        )
        for i, s in enumerate(subs):
            checklist_col.controls.append(_sub_row(s, index=i, total=len(subs)))

    pin_btn = ft.IconButton(
        icon=ft.Icons.PUSH_PIN if pinned_state["value"] else ft.Icons.PUSH_PIN_OUTLINED,
        icon_color=ORANGE if pinned_state["value"] else MUTED,
        tooltip="Открепить" if pinned_state["value"] else "Закрепить",
        on_click=do_toggle_pin,
    )

    return ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.IconButton(
                            icon=ft.Icons.ARROW_BACK_IOS_NEW,
                            icon_color=TEXT,
                            icon_size=18,
                            on_click=lambda e: on_back(),
                        ),
                        ft.Text(
                            "Задача",
                            size=22,
                            weight=ft.FontWeight.W_700,
                            color=TEXT,
                            expand=True,
                        ),
                        pin_btn,
                        ft.IconButton(
                            icon=ft.Icons.CONTENT_COPY,
                            icon_color=MUTED,
                            tooltip="Дублировать",
                            on_click=do_duplicate,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.UNARCHIVE_OUTLINED
                            if archived_state["value"]
                            else ft.Icons.ARCHIVE_OUTLINED,
                            icon_color=MUTED,
                            tooltip="Из архива" if archived_state["value"] else "В архив",
                            on_click=do_archive,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.DELETE_OUTLINE,
                            icon_color=RED,
                            on_click=ask_delete,
                        ),
                    ]
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            title,
                            description,
                            notes_preview,
                            status_dd,
                            priority_dd,
                            goal_dd,
                            color_dd,
                            recur_dd,
                            estimate_field,
                            ft.Row(
                                [
                                    ft.Column(
                                        [
                                            muted("Срок" + (" · просрочено" if overdue else "")),
                                            due_label,
                                        ],
                                        spacing=2,
                                        expand=True,
                                    ),
                                    ft.TextButton("Календарь", on_click=open_picker),
                                    ft.TextButton("Сбросить", on_click=clear_due),
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Row(
                                [
                                    muted("Отложить"),
                                    ft.TextButton(
                                        "+1 день",
                                        on_click=lambda e: do_snooze(1),
                                    ),
                                    ft.TextButton(
                                        "+7 дней",
                                        on_click=lambda e: do_snooze(7),
                                    ),
                                ],
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            completed_info,
                            archived_hint,
                            err,
                        ],
                        spacing=12,
                    ),
                    padding=16,
                    **card_style(),
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                "Чек-лист",
                                size=15,
                                weight=ft.FontWeight.W_700,
                                color=TEXT,
                            ),
                            checklist_col,
                            ft.Row(
                                [
                                    new_sub_field,
                                    ft.Container(
                                        content=ft.Icon(
                                            ft.Icons.ADD_ROUNDED, color="#0F0F12", size=20
                                        ),
                                        width=44,
                                        height=44,
                                        bgcolor=ORANGE,
                                        border_radius=ft.BorderRadius.all(12),
                                        alignment=ft.Alignment.CENTER,
                                        on_click=add_sub,
                                        ink=True,
                                    ),
                                ],
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                        ],
                        spacing=10,
                    ),
                    padding=16,
                    **card_style(),
                ),
                ft.Container(
                    content=ft.Text(
                        "Сохранить", size=15, weight=ft.FontWeight.W_700, color="#0F0F12"
                    ),
                    bgcolor=ORANGE,
                    padding=16,
                    border_radius=ft.BorderRadius.all(14),
                    alignment=ft.Alignment.CENTER,
                    on_click=save,
                    ink=True,
                ),
                ft.Container(height=8),
            ],
            spacing=14,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        ),
        padding=ft.Padding.only(left=16, right=16, top=18, bottom=8),
        expand=True,
    )
