"""Tasks list — status/priority/archive filters, sort, search, overdue chips."""
from __future__ import annotations

import flet as ft

from app.db import get_session
from app.services import task_service
from app.ui.components.cards import empty_state, task_card
from app.ui.components.dialogs import confirm_delete, show_snack
from app.ui.theme import BORDER, GREEN, MUTED, ORANGE, RED, TAG_COLORS, TEXT, muted


def _chip(label: str, *, active: bool, accent: str = ORANGE, on_click=None) -> ft.Container:
    return ft.Container(
        content=ft.Text(
            label,
            size=12,
            color="#0F0F12" if active else MUTED,
            weight=ft.FontWeight.W_500,
        ),
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        border_radius=ft.BorderRadius.all(16),
        bgcolor=accent if active else "transparent",
        border=ft.Border.all(1, accent if active else BORDER),
        on_click=on_click,
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

    status_keys = [None, "todo", "in_progress", "done", "due_today", "overdue", "pinned", "inbox", "archive"]
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
    pri_keys = [None, "high", "medium", "low"]
    pri_labels = [
        ("Все", None),
        ("Высокий", "high"),
        ("Средний", "medium"),
        ("Низкий", "low"),
    ]
    sort_keys = [None, "due", "priority", "created"]
    sort_labels = [
        ("Умная", None),
        ("Срок", "due"),
        ("Приоритет", "priority"),
        ("Создано", "created"),
    ]

    status_chips: list[ft.Container] = []
    pri_chips: list[ft.Container] = []
    sort_chips: list[ft.Container] = []

    def _paint_status():
        mode = filter_mode["value"]
        for i, chip in enumerate(status_chips):
            key = status_keys[i]
            active = mode == key
            if key == "overdue" and active:
                accent = RED
            elif key == "pinned" and active:
                accent = ORANGE
            elif key == "inbox" and active:
                accent = ORANGE
            else:
                accent = ORANGE
            chip.bgcolor = accent if active else "transparent"
            chip.border = ft.Border.all(1, accent if active else BORDER)
            chip.content.color = "#0F0F12" if active else MUTED

    def _paint_pri():
        mode = priority_mode["value"]
        for i, chip in enumerate(pri_chips):
            key = pri_keys[i]
            active = mode == key
            chip.bgcolor = ORANGE if active else "transparent"
            chip.border = ft.Border.all(1, ORANGE if active else BORDER)
            chip.content.color = "#0F0F12" if active else MUTED

    def _paint_sort():
        mode = sort_mode["value"]
        for i, chip in enumerate(sort_chips):
            key = sort_keys[i]
            active = mode == key
            chip.bgcolor = ORANGE if active else "transparent"
            chip.border = ft.Border.all(1, ORANGE if active else BORDER)
            chip.content.color = "#0F0F12" if active else MUTED

    def _paint_select_btn():
        on = select_on["value"]
        select_btn_icon.color = ORANGE if on else TEXT
        select_btn.border = ft.Border.all(1, ORANGE if on else BORDER)
        select_btn.tooltip = "Готово" if on else "Выбрать"

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
            available_tags = task_service.list_color_tags(
                session, archived=(mode == "archive")
            )
        _rebuild_tag_chips(available_tags)
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
        _paint_batch()
        page.update()

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
            show_snack(page, "Ничего не выбрано", error=True)
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
            show_snack(page, "Ничего не выбрано", error=True)
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

    tag_chips: list[ft.Container] = []
    tag_row = ft.Row(tag_chips, spacing=8, scroll=ft.ScrollMode.AUTO)

    def _paint_tags():
        mode = tag_mode["value"]
        for chip in tag_chips:
            key = chip.data
            active = mode == key
            accent = TAG_COLORS.get(key or "", ORANGE) if key else ORANGE
            chip.bgcolor = accent if active else "transparent"
            chip.border = ft.Border.all(1, accent if active else BORDER)
            chip.content.color = "#0F0F12" if active else MUTED

    def set_tag(mode):
        tag_mode["value"] = mode
        _paint_tags()
        reload()

    def _rebuild_tag_chips(tags: list[str]):
        tag_chips.clear()
        tag_row.controls.clear()
        all_chip = _chip(
            "Все метки",
            active=tag_mode["value"] is None,
            on_click=lambda e: set_tag(None),
        )
        all_chip.data = None
        tag_chips.append(all_chip)
        tag_row.controls.append(all_chip)
        for tg in tags:
            chip = _chip(
                tg,
                active=tag_mode["value"] == tg,
                accent=TAG_COLORS.get(tg, ORANGE),
                on_click=lambda e, t=tg: set_tag(t),
            )
            chip.data = tg
            tag_chips.append(chip)
            tag_row.controls.append(chip)
        _paint_tags()


    def set_filter(mode):
        filter_mode["value"] = mode
        if mode == "archive":
            select_on["value"] = False
            selected.clear()
        _paint_status()
        reload()

    def set_priority(mode):
        priority_mode["value"] = mode
        _paint_pri()
        reload()

    def set_sort(mode):
        sort_mode["value"] = mode
        _paint_sort()
        reload()

    def on_search(e):
        search_q["value"] = e.control.value or ""
        reload()

    for label, st in status_labels:
        chip = _chip(label, active=False, on_click=lambda e, s=st: set_filter(s))
        status_chips.append(chip)
    for label, st in pri_labels:
        chip = _chip(label, active=False, on_click=lambda e, s=st: set_priority(s))
        pri_chips.append(chip)
    for label, st in sort_labels:
        chip = _chip(label, active=False, on_click=lambda e, s=st: set_sort(s))
        sort_chips.append(chip)

    _paint_status()
    _paint_pri()
    _paint_sort()

    search = ft.TextField(
        hint_text="Фильтр по названию…",
        prefix_icon=ft.Icons.FILTER_LIST,
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
        on_change=on_search,
        height=48,
        expand=True,
    )

    select_btn.on_click = toggle_select_mode

    header = ft.Row(
        [
            ft.Text("Задачи", size=26, weight=ft.FontWeight.W_700, color=TEXT, expand=True),
            select_btn,
            ft.Container(
                content=ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, color=ORANGE, size=20),
                width=44,
                height=44,
                bgcolor="#1C1C22",
                border=ft.Border.all(1, BORDER),
                border_radius=ft.BorderRadius.all(12),
                alignment=ft.Alignment.CENTER,
                on_click=lambda e: on_open_note("tasks.md", "Задачи") if on_open_note else None,
                ink=True,
                tooltip="Заметка · tasks.md",
            ),
            ft.Container(
                content=ft.Icon(ft.Icons.SEARCH, color=TEXT, size=20),
                width=44,
                height=44,
                bgcolor="#1C1C22",
                border=ft.Border.all(1, BORDER),
                border_radius=ft.BorderRadius.all(12),
                alignment=ft.Alignment.CENTER,
                on_click=lambda e: on_open_search() if on_open_search else None,
                ink=True,
                tooltip="Глобальный поиск",
            ),
            ft.Container(
                content=ft.Icon(ft.Icons.ADD_ROUNDED, color="#0F0F12", size=22),
                width=44,
                height=44,
                bgcolor=ORANGE,
                border_radius=ft.BorderRadius.all(12),
                alignment=ft.Alignment.CENTER,
                on_click=lambda e: on_add(),
                ink=True,
            ),
        ],
        spacing=8,
    )

    root = ft.Container(
        content=ft.Column(
            [
                header,
                muted("Статус · метка · приоритет · сортировка · закреп · выбор"),
                ft.Row([search], spacing=8),
                ft.Row(status_chips, spacing=8, scroll=ft.ScrollMode.AUTO),
                muted("Метка"),
                tag_row,
                muted("Приоритет"),
                ft.Row(pri_chips, spacing=8, scroll=ft.ScrollMode.AUTO),
                muted("Сортировка"),
                ft.Row(sort_chips, spacing=8, scroll=ft.ScrollMode.AUTO),
                batch_host,
                list_col,
            ],
            spacing=12,
            expand=True,
        ),
        padding=ft.Padding.only(left=16, right=16, top=18, bottom=8),
        expand=True,
    )
    reload()
    return root
