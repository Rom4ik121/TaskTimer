"""Tasks list — filters live in a dedicated sheet; main UI stays the list."""
from __future__ import annotations

import flet as ft

from app.db import get_session
from app.services import task_service
from app.ui.components.cards import empty_state, task_card
from app.ui.components.dialogs import (
    confirm_delete,
    show_filter_sheet,
    show_snack,
    validation_fail,
)
from app.ui.theme import (
    BORDER,
    GREEN,
    ORANGE,
    RED,
    TAG_COLORS,
    TEXT,
    header_icon_btn,
    screen_header,
    screen_insets,
)


STATUS_FILTER_LABELS: list[tuple[str, str | None]] = [
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
PRIORITY_FILTER_LABELS: list[tuple[str, str | None]] = [
    ("Все", None),
    ("Высокий", "high"),
    ("Средний", "medium"),
    ("Низкий", "low"),
]
SORT_FILTER_LABELS: list[tuple[str, str | None]] = [
    ("Умная", None),
    ("Срок", "due"),
    ("Приоритет", "priority"),
    ("Создано", "created"),
]


def _label_of(pairs: list[tuple[str, str | None]], value) -> str | None:
    for label, key in pairs:
        if key == value:
            return None if key is None else label
    return str(value) if value is not None else None


def compact_filter_summary(
    status=None,
    priority=None,
    sort=None,
    tag=None,
) -> str | None:
    """One-line RU summary of non-default list filters, or None if all default."""
    parts: list[str] = []
    st = _label_of(STATUS_FILTER_LABELS, status)
    if st:
        parts.append(st)
    pr = _label_of(PRIORITY_FILTER_LABELS, priority)
    if pr:
        parts.append(pr)
    so = _label_of(SORT_FILTER_LABELS, sort)
    if so:
        parts.append(so)
    if tag:
        parts.append(str(tag))
    if not parts:
        return None
    return "Фильтр: " + " · ".join(parts)


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
    filter_btn_icon = ft.Icon(ft.Icons.FILTER_LIST, color=TEXT, size=20)
    filter_btn = ft.Container(
        content=filter_btn_icon,
        width=44,
        height=44,
        bgcolor="#1C1C22",
        border=ft.Border.all(1, BORDER),
        border_radius=ft.BorderRadius.all(12),
        alignment=ft.Alignment.CENTER,
        ink=True,
        tooltip="Фильтры",
    )

    def _filters_active() -> bool:
        return any(
            (
                filter_mode["value"] is not None,
                priority_mode["value"] is not None,
                sort_mode["value"] is not None,
                tag_mode["value"] is not None,
            )
        )

    def _paint_select_btn():
        on = select_on["value"]
        select_btn_icon.color = ORANGE if on else TEXT
        select_btn.border = ft.Border.all(1, ORANGE if on else BORDER)
        select_btn.tooltip = "Готово" if on else "Выбрать"

    def _paint_filter_btn():
        on = _filters_active()
        filter_btn_icon.color = ORANGE if on else TEXT
        filter_btn.border = ft.Border.all(1, ORANGE if on else BORDER)
        filter_btn.tooltip = "Фильтры · активны" if on else "Фильтры"

    def _paint_summary():
        text = compact_filter_summary(
            filter_mode["value"],
            priority_mode["value"],
            sort_mode["value"],
            tag_mode["value"],
        )
        if not text:
            summary_host.visible = False
            summary_host.content = None
            return
        summary_host.visible = True
        summary_host.content = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.FILTER_LIST, color=ORANGE, size=14),
                    ft.Text(
                        text,
                        size=12,
                        weight=ft.FontWeight.W_600,
                        color=TEXT,
                        expand=True,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            bgcolor="#1C1C22",
            border=ft.Border.all(1, ORANGE),
            border_radius=ft.BorderRadius.all(16),
            on_click=open_filters,
            ink=True,
            tooltip="Изменить фильтры",
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
            for t in tasks:
                list_col.controls.append(
                    task_card(
                        t,
                        on_tap=None if select_on["value"] else on_open_task,
                        on_cycle_status=None if select_on["value"] else cycle,
                        on_delete=None if select_on["value"] else delete,
                        on_toggle_pin=None if select_on["value"] else toggle_pin,
                        select_mode=select_on["value"],
                        selected=t.id in selected,
                        on_toggle_select=toggle_selected,
                    )
                )
        _paint_select_btn()
        _paint_filter_btn()
        _paint_summary()
        _paint_batch()
        page.update()

    def apply_filters(values: dict):
        filter_mode["value"] = values.get("status")
        priority_mode["value"] = values.get("priority")
        sort_mode["value"] = values.get("sort")
        tag_mode["value"] = values.get("tag")
        if filter_mode["value"] == "archive":
            select_on["value"] = False
            selected.clear()
        reload()

    def open_filters(_e=None):
        mode = filter_mode["value"]
        with get_session() as session:
            tags = task_service.list_color_tags(
                session, archived=(mode == "archive")
            )
        tag_options: list[tuple[str, str | None]] = [("Все метки", None)]
        tag_accents: dict = {}
        for tg in tags:
            tag_options.append((tg, tg))
            tag_accents[tg] = TAG_COLORS.get(tg, ORANGE)
        show_filter_sheet(
            page,
            title="Фильтры",
            subtitle="Статус, приоритет, сортировка и теги",
            sections=[
                {
                    "key": "status",
                    "title": "Статус",
                    "options": STATUS_FILTER_LABELS,
                    "value": filter_mode["value"],
                    "accents": {"overdue": RED},
                },
                {
                    "key": "priority",
                    "title": "Приоритет",
                    "options": PRIORITY_FILTER_LABELS,
                    "value": priority_mode["value"],
                },
                {
                    "key": "sort",
                    "title": "Сортировка",
                    "options": SORT_FILTER_LABELS,
                    "value": sort_mode["value"],
                },
                {
                    "key": "tag",
                    "title": "Теги",
                    "options": tag_options,
                    "value": tag_mode["value"],
                    "accents": tag_accents,
                },
            ],
            reset_values={
                "status": None,
                "priority": None,
                "sort": None,
                "tag": None,
            },
            on_apply=apply_filters,
        )

    def toggle_pin(tid: int, pinned: bool):
        with get_session() as session:
            task_service.set_pinned(session, tid, pinned)
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

    def on_search(e):
        search_q["value"] = e.control.value or ""
        reload()

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
    filter_btn.on_click = open_filters

    header = screen_header(
        "Задачи",
        subtitle="поиск · выбор",
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
            header_icon_btn(
                ft.Icons.ADD_ROUNDED,
                on_click=lambda e: on_add(),
                tooltip="Создать",
                accent=True,
                icon_size=22,
            ),
        ],
    )

    root = ft.Container(
        content=ft.Column(
            [
                header,
                ft.Row([search], spacing=8),
                summary_host,
                batch_host,
                list_col,
            ],
            spacing=10,
            expand=True,
        ),
        padding=screen_insets(),
        expand=True,
    )
    reload()
    return root
