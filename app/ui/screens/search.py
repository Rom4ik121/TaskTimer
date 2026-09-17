"""Global search overlay — find tasks + goals by title; recent query chips."""
from __future__ import annotations

import flet as ft

from app.db import get_session
from app.services import search_service
from app.ui.components.cards import empty_state
from app.ui.theme import BORDER, MUTED, ORANGE, TEXT, card_style, muted, section_title


def build_search(
    page: ft.Page,
    *,
    on_back,
    on_open_task=None,
    on_open_goal=None,
) -> ft.Control:
    state = {"q": ""}
    results = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)
    recent_host = ft.Column(spacing=8, visible=False)
    field = ft.TextField(
        hint_text="Поиск задач и целей…",
        prefix_icon=ft.Icons.SEARCH,
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
        autofocus=True,
        height=48,
        on_submit=lambda e: _submit(e.control.value or ""),
    )

    def _load_recent() -> list[str]:
        with get_session() as session:
            return search_service.get_recent_searches(session)

    def _remember(q: str) -> None:
        q = (q or "").strip()
        if not q:
            return
        with get_session() as session:
            search_service.remember_search(session, q)

    def _paint_recent(recent: list[str] | None = None):
        recent_host.controls.clear()
        items = recent if recent is not None else _load_recent()
        if not items:
            recent_host.visible = False
            return
        chips: list[ft.Control] = []
        for q in items:

            def _on_chip(_e, query=q):
                field.value = query
                _submit(query)

            chips.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.HISTORY, color=MUTED, size=14),
                            ft.Text(
                                q,
                                size=12,
                                color=TEXT,
                                weight=ft.FontWeight.W_500,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                        ],
                        spacing=6,
                        tight=True,
                    ),
                    padding=ft.Padding.symmetric(horizontal=10, vertical=7),
                    border_radius=ft.BorderRadius.all(16),
                    border=ft.Border.all(1, BORDER),
                    bgcolor="#1C1C22",
                    on_click=_on_chip,
                    ink=True,
                )
            )
        recent_host.controls.extend(
            [
                muted("Недавние"),
                ft.Row(chips, spacing=8, scroll=ft.ScrollMode.AUTO, wrap=False),
            ]
        )
        recent_host.visible = True

    def _submit(q: str):
        q = (q or "").strip()
        if q:
            _remember(q)
        _run(q, remembered=True)

    def _run(q: str, *, remembered: bool = False):
        state["q"] = (q or "").strip()
        results.controls.clear()
        with get_session() as session:
            data = search_service.search(session, state["q"])
        tasks = data["tasks"]
        goals = data["goals"]
        if not state["q"]:
            _paint_recent()
            results.controls.append(
                empty_state("Начните вводить", "Поиск по названию задач и целей", emoji="🔍")
            )
            page.update()
            return
        # hide recent while typing / results
        recent_host.visible = False
        recent_host.controls.clear()
        if not tasks and not goals:
            results.controls.append(
                empty_state("Ничего не найдено", f"Нет совпадений для «{state['q']}»", emoji="🕳️")
            )
            page.update()
            return

        def _open_goal(gid: int):
            if not remembered:
                _remember(state["q"])
            if on_open_goal:
                on_open_goal(gid)

        def _open_task(tid: int):
            if not remembered:
                _remember(state["q"])
            if on_open_task:
                on_open_task(tid)

        if goals:
            results.controls.append(section_title(f"Цели · {len(goals)}"))
            for g in goals:
                results.controls.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.FLAG_OUTLINED, color=ORANGE, size=18),
                                ft.Column(
                                    [
                                        ft.Text(
                                            g.title,
                                            size=14,
                                            weight=ft.FontWeight.W_600,
                                            color=TEXT,
                                            max_lines=1,
                                            overflow=ft.TextOverflow.ELLIPSIS,
                                        ),
                                        muted(
                                            f"{g.percent_complete:.0f}% · {g.unit}"
                                            + (" · архив" if g.archived else "")
                                        ),
                                    ],
                                    spacing=2,
                                    expand=True,
                                ),
                                ft.Icon(ft.Icons.CHEVRON_RIGHT, color=MUTED, size=18),
                            ],
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=14,
                        **card_style(),
                        on_click=lambda e, gid=g.id: _open_goal(gid),
                        ink=True,
                    )
                )

        if tasks:
            results.controls.append(section_title(f"Задачи · {len(tasks)}"))
            for t in tasks:
                due = t.due_date.isoformat() if t.due_date else "без срока"
                results.controls.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, color=ORANGE, size=18),
                                ft.Column(
                                    [
                                        ft.Text(
                                            t.title,
                                            size=14,
                                            weight=ft.FontWeight.W_600,
                                            color=TEXT,
                                            max_lines=1,
                                            overflow=ft.TextOverflow.ELLIPSIS,
                                        ),
                                        muted(
                                            f"{t.status} · {t.priority} · {due}"
                                            + (" · архив" if t.archived else "")
                                        ),
                                    ],
                                    spacing=2,
                                    expand=True,
                                ),
                                ft.Icon(ft.Icons.CHEVRON_RIGHT, color=MUTED, size=18),
                            ],
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=14,
                        **card_style(),
                        on_click=lambda e, tid=t.id: _open_task(tid),
                        ink=True,
                    )
                )
        page.update()

    def on_change(e):
        _run(e.control.value or "")

    field.on_change = on_change

    header = ft.Row(
        [
            ft.IconButton(
                icon=ft.Icons.ARROW_BACK_IOS_NEW,
                icon_color=TEXT,
                icon_size=18,
                on_click=lambda e: on_back(),
            ),
            ft.Text("Поиск", size=22, weight=ft.FontWeight.W_700, color=TEXT, expand=True),
        ],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    _run("")

    return ft.Container(
        content=ft.Column(
            [header, field, muted("Задачи и цели по названию"), recent_host, results],
            spacing=12,
            expand=True,
        ),
        padding=ft.Padding.only(left=16, right=16, top=18, bottom=8),
        expand=True,
    )
