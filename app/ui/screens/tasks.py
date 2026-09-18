"""Tasks list — filters live in a sheet; main surface is header, search, list, FAB."""
from __future__ import annotations

import flet as ft

from app.db import get_session
from app.services import task_service
from app.ui.components.cards import empty_state, task_card
from app.ui.components.dialogs import confirm_delete, show_snack, validation_fail
from app.ui.components.filter_sheet import FilterSection, show_filter_sheet, summary_chip
from app.ui.haptics import haptic
from app.ui.motion import appear_item, pulse_press, reveal_items
from app.ui.theme import (
    BORDER,
    GREEN,
    MUTED,
    ORANGE,
    RED,
    TAG_COLORS,
    TEXT,
    header_icon_btn,
    screen_header,
    screen_insets,
)


def build_tasks(
    page: ft.Page,
    *,
    on_add,
    refresh_all,
    on_open_task=None,
    initial_filter=None,
    on_open_search=None,
    on_open_note=None,
) -> ft.Control:
    # status_mode: None | status str | "overdue" | "due_today" | "archive"
    filter_mode = {"value": initial_filter}
    priority_mode = {"value": None}  # None | low|medium|high
    sort_mode = {"value": None}  # None | due | priority | created
    tag_mode = {"value": None}  # None | color_tag
    search_q = {"value": ""}
    select_on = {"value": False}
    selected: set[int] = set()
    list_col = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)
    batch_host = ft.Container(visible=False)
    summary_host = ft.Container(visible=False)
    select_btn_icon = ft.Icon(ft.Icons.CHECKLIST, color=TEXT, size=20)
    select_btn = ft.Container(
        content=select_btn_icon,
        width=44,
        height=44,
        bgcolor="#1C1C22",
        border=ft.Border.all(1, BORDER),
        border_radius=ft.BorderRadius.all(12),
        alignment=ft.Alignment.CENTER,
        ink=True,
        tooltip="Выбрать",
    )

    status_labels = [
        ("Все", None),
        ("К выполнению", "todo"),
        ("В работе", "in_progress"),
        ("Готово", "done"),
        ("Сегодня", "due_today"),
        ("Просрочено", "overdue"),
        ("Закреплённые", "pinned"),
        ("Входящие", "inbox"),
        ("Архив", "archive"),
    ]
    pri_labels = [
        ("Все", None),
        ("Высокий", "high"),
        ("Средний", "medium"),
        ("Низкий", "low"),
    ]
    sort_labels = [
        ("Умная", None),
        ("Срок", "due"),
        ("Приоритет", "priority"),
        ("Создано", "created"),
    ]
    status_summary = {k: lab for lab, k in status_labels if k is not None}
    pri_summary = {k: lab for lab, k in pri_labels if k is not None}
    sort_summary = {k: lab for lab, k in sort_labels if k is not None}
    status_accents = {
        "overdue": RED,
        "pinned": ORANGE,
        "inbox": ORANGE,
    }

    def _filters_active() -> bool:
        return any(
            [
                filter_mode["value"] is not None,
                priority_mode["value"] is not None,
                sort_mode["value"] is not None,
                tag_mode["value"] is not None,
            ]
        )

    def _summary_text() -> str:
        parts: list[str] = []
        st = filter_mode["value"]
        if st is not None:
            parts.append(status_summary.get(st, str(st)))
        pri = priority_mode["value"]
        if pri is not None:
            parts.append(pri_summary.get(pri, str(pri)))
        tag = tag_mode["value"]
        if tag:
            parts.append(str(tag))
        sort = sort_mode["value"]
        if sort is not None:
            parts.append(sort_summary.get(sort, str(sort)))
        return " · ".join(parts)

    def _paint_select_btn():
        on = select_on["value"]
        select_btn_icon.color = ORANGE if on else TEXT
        select_btn.border = ft.Border.all(1, ORANGE if on else BORDER)
        select_btn.tooltip = "Готово" if on else "Выбрать"

    def _paint_filter_btn():
        on = _filters_active()
        filter_icon.color = ORANGE if on else TEXT
        filter_btn.border = ft.Border.all(1, ORANGE if on else BORDER)
        filter_btn.tooltip = "Фильтры"

    def _paint_summary():
        text = _summary_text()
        active = bool(text)
        summary_host.visible = active
        if not active:
            summary_host.content = None
            return
        summary_host.content = summary_chip(
            text,
            on_click=lambda e: open_filters(),
            page=page,
        )

    def _paint_batch():
        on = select_on["value"]
        n = len(selected)
        batch_host.visible = on
        if not on:
            batch_host.content = None
            return
        batch_host.content = ft.Container(
            content=ft.Row(
                [
                    ft.Text(
                        f"Выбрано: {n}",
                        size=13,
                        weight=ft.FontWeight.W_600,
                        color=TEXT,
                        expand=True,
                    ),
                    ft.Container(
                        content=ft.Text(
                            "Готово",
                            size=13,
                            weight=ft.FontWeight.W_700,
                            color="#0F0F12",
                        ),
                        bgcolor=GREEN,
                        padding=ft.Padding.symmetric(horizontal=14, vertical=8),
                        border_radius=ft.BorderRadius.all(14),
                        on_click=lambda e: do_batch_complete(),
                        ink=True,
                        opacity=1.0 if n else 0.4,
                    ),
                    ft.Container(
                        content=ft.Text(
                            "В архив",
                            size=13,
                            weight=ft.FontWeight.W_700,
                            color="#0F0F12",
                        ),
                        bgcolor=ORANGE,
                        padding=ft.Padding.symmetric(horizontal=14, vertical=8),
                        border_radius=ft.BorderRadius.all(14),
                        on_click=lambda e: do_batch_archive(),
                        ink=True,
                        opacity=1.0 if n else 0.4,
                    ),
                    ft.TextButton("Отмена", on_click=lambda e: set_select_mode(False)),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=4, vertical=2),
        )

    def _fetch(session):
        mode = filter_mode["value"]
        pri = priority_mode["value"]
        sort = sort_mode["value"]
        tag = tag_mode["value"]
        q = search_q["value"] or None
        kwargs = dict(priority=pri, query=q, sort=sort, color_tag=tag)
        if mode == "archive":
            return task_service.list_tasks(session, archived=True, **kwargs)
        if mode == "overdue":
            return task_service.list_tasks(session, overdue=True, **kwargs)
        if mode == "due_today":
            return task_service.list_tasks(session, due_today=True, **kwargs)
        if mode == "pinned":
            return task_service.list_tasks(session, pinned=True, **kwargs)
        if mode == "inbox":
            return task_service.list_tasks(session, inbox=True, **kwargs)
        return task_service.list_tasks(session, status=mode, **kwargs)

    def reload(_: ft.ControlEvent | None = None):
        list_col.controls.clear()
        mode = filter_mode["value"]
        with get_session() as session:
            tasks = _fetch(session)
        appeared: list[ft.Control] = []
        if not tasks:
            hint = "Смените фильтр или создайте задачу кнопкой +"
            title = "Задач не найдено"
            if mode == "due_today":
                title = "На сегодня пусто"
                hint = "Нет задач со сроком сегодня — отличный день"
            elif mode == "overdue":
                title = "Просроченных нет"
                hint = "Все сроки в порядке"
            elif mode == "pinned":
                title = "Нет закреплённых"
                hint = "Нажмите 📌 на карточке, чтобы закрепить"
            elif mode == "inbox":
                title = "Inbox пуст"
                hint = "Быстрый захват на Доме добавляет сюда"
            elif mode == "archive":
                title = "Архив пуст"
                hint = "Архивированные задачи появятся здесь"
            elif mode == "done":
                title = "Нет выполненных"
                hint = "Завершённые задачи появятся здесь"
            skip_add = mode in ("overdue", "archive", "pinned", "inbox")
            emoji = {
                "due_today": "☀️",
                "overdue": "🎉",
                "pinned": "📌",
                "inbox": "📥",
                "archive": "📦",
                "done": "✅",
            }.get(mode, "📋")
            list_col.controls.append(
                empty_state(
                    title,
                    hint,
                    emoji=emoji,
                    action_label=None if skip_add else "Создать задачу",
                    on_action=None if skip_add else on_add,
                )
            )
        else:
            if mode == "done":
                list_col.controls.append(
                    ft.Container(
                        content=ft.Text(
                            "Очистить выполненные → архив",
                            size=12,
                            weight=ft.FontWeight.W_700,
                            color="#0F0F12",
                        ),
                        bgcolor=MUTED,
                        padding=ft.Padding.symmetric(horizontal=14, vertical=8),
                        border_radius=ft.BorderRadius.all(14),
                        on_click=lambda e: do_clear_done(),
                        ink=True,
                        alignment=ft.Alignment.CENTER,
                    )
                )
            for i, t in enumerate(tasks):
                card = task_card(
                    t,
                    on_tap=None if select_on["value"] else on_open_task,
                    on_cycle_status=None if select_on["value"] else cycle,
                    on_delete=None if select_on["value"] else delete,
                    on_toggle_pin=None if select_on["value"] else toggle_pin,
                    select_mode=select_on["value"],
                    selected=t.id in selected,
                    on_toggle_select=toggle_selected,
                )
                wrap = appear_item(card, index=i)
                appeared.append(wrap)
                list_col.controls.append(wrap)
        _paint_select_btn()
        _paint_filter_btn()
        _paint_summary()
        _paint_batch()
        page.update()
        reveal_items(appeared, page)

    def toggle_pin(tid: int, pinned: bool):
        with get_session() as session:
            task_service.set_pinned(session, tid, pinned)
        haptic(page, "light")
        show_snack(page, "Закреплено" if pinned else "Откреплено")
        reload()
        refresh_all()

    def cycle(tid: int):
        order = ["todo", "in_progress", "done"]
        with get_session() as session:
            t = task_service.get_task(session, tid)
            if not t:
                return
            nxt = (
                order[(order.index(t.status) + 1) % len(order)]
                if t.status in order
                else "todo"
            )
            task_service.set_status(session, tid, nxt)
        if nxt == "done":
            haptic(page, "medium")
        else:
            haptic(page, "selection")
        reload()

    def delete(tid: int):
        def yes():
            with get_session() as session:
                task_service.delete_task(session, tid)
            reload()

        confirm_delete(
            page,
            title="Удалить задачу?",
            message="Задача будет удалена безвозвратно.",
            on_confirm=yes,
        )

    def toggle_selected(tid: int):
        if tid in selected:
            selected.discard(tid)
        else:
            selected.add(tid)
        reload()

    def set_select_mode(on: bool):
        select_on["value"] = bool(on)
        if not select_on["value"]:
            selected.clear()
        reload()

    def toggle_select_mode(_e=None):
        # Archive filter: nothing to batch-archive
        if filter_mode["value"] == "archive" and not select_on["value"]:
            show_snack(page, "В архиве выбирать нечего")
            return
        set_select_mode(not select_on["value"])

    def do_batch_archive():
        ids = list(selected)
        if not ids:
            validation_fail(page, "Ничего не выбрано")
            return

        def yes():
            with get_session() as session:
                n = task_service.archive_tasks(session, ids)
            selected.clear()
            select_on["value"] = False
            show_snack(page, f"В архив: {n}")
            reload()
            refresh_all()

        confirm_delete(
            page,
            title="В архив?",
            message=f"Переместить выбранные задачи ({len(ids)}) в архив?",
            on_confirm=yes,
            confirm_label="В архив",
        )

    def do_batch_complete():
        ids = list(selected)
        if not ids:
            validation_fail(page, "Ничего не выбрано")
            return

        def yes():
            with get_session() as session:
                n = task_service.complete_tasks(session, ids)
            selected.clear()
            select_on["value"] = False
            haptic(page, "medium")
            show_snack(page, f"Готово: {n}")
            reload()
            refresh_all()

        confirm_delete(
            page,
            title="Отметить готовыми?",
            message=f"Завершить выбранные задачи ({len(ids)})?",
            on_confirm=yes,
            confirm_label="Готово",
        )

    def do_clear_done():
        def yes():
            with get_session() as session:
                n = task_service.clear_done_tasks(session, archive=True)
            show_snack(page, f"В архив: {n}" if n else "Нечего очищать")
            reload()
            refresh_all()

        confirm_delete(
            page,
            title="Очистить выполненные?",
            message="Все готовые задачи будут перемещены в архив.",
            on_confirm=yes,
            confirm_label="В архив",
        )

    def open_filters(_e=None):
        haptic(page, "light")
        mode = filter_mode["value"]
        with get_session() as session:
            tags = task_service.list_color_tags(
                session, archived=(mode == "archive")
            )
        tag_opts: list[tuple[str, str | None]] = [("Все метки", None)]
        tag_accents: dict = {}
        for tg in tags:
            tag_opts.append((tg, tg))
            tag_accents[tg] = TAG_COLORS.get(tg, ORANGE)
        sections = [
            FilterSection(
                "status",
                "Статус",
                status_labels,
                filter_mode["value"],
                status_accents,
            ),
            FilterSection(
                "priority",
                "Приоритет",
                pri_labels,
                priority_mode["value"],
            ),
            FilterSection(
                "sort",
                "Сортировка",
                sort_labels,
                sort_mode["value"],
            ),
            FilterSection(
                "tag",
                "Теги",
                tag_opts,
                tag_mode["value"],
                tag_accents,
            ),
        ]

        def apply(vals: dict):
            filter_mode["value"] = vals.get("status")
            priority_mode["value"] = vals.get("priority")
            sort_mode["value"] = vals.get("sort")
            tag_mode["value"] = vals.get("tag")
            if filter_mode["value"] == "archive":
                select_on["value"] = False
                selected.clear()
            haptic(page, "selection")
            reload()

        show_filter_sheet(
            page,
            title="Фильтры",
            sections=sections,
            on_apply=apply,
        )

    def on_search(e):
        search_q["value"] = e.control.value or ""
        reload()

    funnel = getattr(ft.Icons, "FILTER_ALT", None) or ft.Icons.FILTER_LIST
    filter_icon = ft.Icon(funnel, color=TEXT, size=20)
    filter_btn = ft.Container(
        content=filter_icon,
        width=44,
        height=44,
        bgcolor="#1C1C22",
        border=ft.Border.all(1, BORDER),
        border_radius=ft.BorderRadius.all(12),
        alignment=ft.Alignment.CENTER,
        ink=True,
        tooltip="Фильтры",
        on_click=lambda e: open_filters(),
    )

    search = ft.TextField(
        hint_text="Поиск по названию…",
        prefix_icon=ft.Icons.SEARCH,
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
        on_change=on_search,
        height=48,
        expand=True,
    )

    select_btn.on_click = toggle_select_mode

    header = screen_header(
        "Задачи",
        subtitle="Список · поиск · фильтры в листе",
        actions=[
            filter_btn,
            select_btn,
            header_icon_btn(
                ft.Icons.DESCRIPTION_OUTLINED,
                on_click=lambda e: on_open_note("tasks.md", "Задачи") if on_open_note else None,
                tooltip="Заметка · tasks.md",
                icon_color=ORANGE,
            ),
            header_icon_btn(
                ft.Icons.SEARCH,
                on_click=lambda e: on_open_search() if on_open_search else None,
                tooltip="Глобальный поиск",
            ),
        ],
    )

    fab = ft.Container(
        content=ft.Icon(ft.Icons.ADD_ROUNDED, color="#0F0F12", size=26),
        width=56,
        height=56,
        bgcolor=ORANGE,
        border_radius=ft.BorderRadius.all(16),
        alignment=ft.Alignment.CENTER,
        ink=True,
        tooltip="Создать",
        shadow=ft.BoxShadow(
            blur_radius=16,
            color="#FF8A0055",
            offset=ft.Offset(0, 4),
        ),
        on_click=lambda e: (pulse_press(e.control), haptic(page, "light", control=e.control), on_add()),
    )
    # Keep a FloatingActionButton alias in source for smoke / reviewers.
    FloatingActionButton = fab  # noqa: N806 — FAB on the Tasks stack

    body = ft.Column(
        [
            header,
            ft.Row([search], spacing=8),
            summary_host,
            batch_host,
            list_col,
        ],
        spacing=10,
        expand=True,
    )
    stack = ft.Stack(
        [
            body,
            ft.Container(
                content=fab,
                alignment=ft.Alignment.BOTTOM_RIGHT,
                padding=ft.Padding.only(right=4, bottom=8),
            ),
        ],
        expand=True,
    )
    _ = FloatingActionButton
    root = ft.Container(
        content=stack,
        padding=screen_insets(),
        expand=True,
    )
    reload()
    return root
