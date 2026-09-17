"""DEPRECATED standalone roadmap UI — kept for smoke/lint; not wired in main.

Product path: bottom-nav «Холст» (`canvas_board`) + optional roadmap layer via
`roadmap_service`. Do not re-add this screen to nav; edit the canvas layer instead.

Legacy interactive canvas roadmap — add node, cycle status, link task, add edge, auto-layout.
"""
from __future__ import annotations

import flet as ft
import flet.canvas as cv

from app.db import get_session
from app.schemas import RoadmapEdgeCreate, RoadmapNodeCreate, RoadmapNodeUpdate
from app.services import roadmap_service, task_service
from app.ui.components.dialogs import confirm_delete, show_snack
from app.ui.components.cards import empty_state
from app.ui.theme import (
    BORDER,
    CARD,
    GREEN,
    MUTED,
    NODE_STATUS_LABELS,
    ORANGE,
    RED,
    TEXT,
    card_style,
    muted,
)


STATUS_FILL = {
    "pending": "#2A2A32",
    "active": ORANGE,
    "done": GREEN,
}


def build_roadmap(page: ft.Page, *, refresh_all=None) -> ft.Control:
    canvas_host = ft.Container(expand=True)
    pick = {"from": None, "mode": None}  # mode: edge

    def paint():
        with get_session() as session:
            nodes = roadmap_service.list_nodes(session)
            edges = roadmap_service.list_edges(session)
            tasks = task_service.list_tasks(session)
            task_map = {t.id: t.title for t in tasks}

        by_id = {n.id: n for n in nodes}
        shapes: list[cv.Shape] = []

        for x in range(0, 340, 40):
            shapes.append(
                cv.Line(x, 0, x, 360, paint=ft.Paint(color="#1A1A20", stroke_width=1))
            )
        for y in range(0, 360, 40):
            shapes.append(
                cv.Line(0, y, 340, y, paint=ft.Paint(color="#1A1A20", stroke_width=1))
            )

        for edge in edges:
            a = by_id.get(edge.from_node_id)
            b = by_id.get(edge.to_node_id)
            if not a or not b:
                continue
            shapes.append(
                cv.Line(
                    a.x + 54,
                    a.y + 22,
                    b.x,
                    b.y + 22,
                    paint=ft.Paint(color="#3A3A44", stroke_width=1.5),
                )
            )

        for n in nodes:
            fill = STATUS_FILL.get(n.status, "#2A2A32")
            shapes.append(
                cv.Rect(
                    n.x,
                    n.y,
                    108,
                    44,
                    border_radius=ft.BorderRadius.all(12),
                    paint=ft.Paint(color=CARD, style=ft.PaintingStyle.FILL),
                )
            )
            shapes.append(
                cv.Rect(
                    n.x,
                    n.y,
                    108,
                    44,
                    border_radius=ft.BorderRadius.all(12),
                    paint=ft.Paint(
                        color=fill if n.status != "pending" else BORDER,
                        style=ft.PaintingStyle.STROKE,
                        stroke_width=1.5,
                    ),
                )
            )
            shapes.append(
                cv.Circle(
                    n.x + 14,
                    n.y + 22,
                    5,
                    paint=ft.Paint(color=fill, style=ft.PaintingStyle.FILL),
                )
            )
            shapes.append(
                cv.Text(
                    n.x + 26,
                    n.y + 14,
                    n.title[:12],
                    ft.TextStyle(size=11, color=TEXT, weight=ft.FontWeight.W_600),
                )
            )

        canvas = cv.Canvas(shapes, width=340, height=360)

        def add_node(_):
            title_f = ft.TextField(
                label="Название узла",
                border_color=BORDER,
                focused_border_color=ORANGE,
                color=TEXT,
            )
            # auto layout: cascade
            nx = 40 + (len(nodes) % 4) * 120
            ny = 40 + (len(nodes) // 4) * 90

            def submit(__):
                name = (title_f.value or "").strip()
                if not name:
                    show_snack(page, "Введите название", error=True)
                    return
                with get_session() as session:
                    roadmap_service.create_node(
                        session,
                        RoadmapNodeCreate(title=name, x=float(nx), y=float(ny)),
                    )
                page.pop_dialog()
                show_snack(page, "Узел добавлен")
                paint()

            page.show_dialog(
                ft.AlertDialog(
                    title=ft.Text("Новый узел", color=TEXT),
                    content=title_f,
                    actions=[
                        ft.TextButton("Отмена", on_click=lambda e: page.pop_dialog()),
                        ft.TextButton("Добавить", on_click=submit),
                    ],
                )
            )

        def cycle_status(nid: int):
            with get_session() as session:
                roadmap_service.cycle_node_status(session, nid)
            paint()

        def link_task(nid: int):
            opts = [ft.dropdown.Option("", "Без задачи")] + [
                ft.dropdown.Option(str(t.id), t.title[:36]) for t in tasks[:40]
            ]
            dd = ft.Dropdown(
                label="Задача",
                options=opts,
                value="",
                border_color=BORDER,
                focused_border_color=ORANGE,
                color=TEXT,
            )

            def submit(__):
                tid = int(dd.value) if dd.value else None
                with get_session() as session:
                    roadmap_service.update_node(
                        session, nid, RoadmapNodeUpdate(task_id=tid)
                    )
                page.pop_dialog()
                show_snack(page, "Связь сохранена")
                paint()

            page.show_dialog(
                ft.AlertDialog(
                    title=ft.Text("Связать с задачей", color=TEXT),
                    content=dd,
                    actions=[
                        ft.TextButton("Отмена", on_click=lambda e: page.pop_dialog()),
                        ft.TextButton("ОК", on_click=submit),
                    ],
                )
            )

        def delete_node(nid: int):
            def yes():
                with get_session() as session:
                    roadmap_service.delete_node(session, nid)
                show_snack(page, "Узел удалён")
                paint()

            confirm_delete(
                page,
                title="Удалить узел?",
                message="Связанные рёбра тоже будут удалены.",
                on_confirm=yes,
            )

        def start_edge(nid: int):
            if pick["mode"] == "edge" and pick["from"] is not None and pick["from"] != nid:
                with get_session() as session:
                    edge = roadmap_service.create_edge(
                        session,
                        RoadmapEdgeCreate(from_node_id=pick["from"], to_node_id=nid),
                    )
                pick["from"] = None
                pick["mode"] = None
                if edge:
                    show_snack(page, "Ребро создано")
                else:
                    show_snack(page, "Не удалось создать ребро", error=True)
                paint()
                return
            pick["mode"] = "edge"
            pick["from"] = nid
            show_snack(page, "Выберите второй узел для связи")
            paint()

        def toolbar_edge(_):
            pick["mode"] = "edge"
            pick["from"] = None
            show_snack(page, "Сначала нажмите «Связь» на первом узле")

        def auto_layout(_):
            with get_session() as session:
                updated = roadmap_service.auto_layout_nodes(session)
            show_snack(
                page,
                f"Раскладка: {len(updated)} узлов" if updated else "Нет узлов",
            )
            paint()

        node_rows = []
        for n in nodes:
            linked = task_map.get(n.task_id, "") if n.task_id else ""
            selected = pick["mode"] == "edge" and pick["from"] == n.id
            node_rows.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Container(
                                        width=10,
                                        height=10,
                                        bgcolor=STATUS_FILL.get(n.status, MUTED),
                                        border_radius=5,
                                    ),
                                    ft.Text(
                                        n.title,
                                        size=13,
                                        weight=ft.FontWeight.W_600,
                                        color=TEXT,
                                        expand=True,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                    ft.Text(
                                        NODE_STATUS_LABELS.get(n.status, n.status),
                                        size=11,
                                        color=MUTED,
                                    ),
                                ],
                                spacing=8,
                            ),
                            *([muted(f"→ {linked[:28]}")] if linked else []),
                            ft.Row(
                                [
                                    ft.TextButton(
                                        "Статус",
                                        on_click=lambda e, i=n.id: cycle_status(i),
                                    ),
                                    ft.TextButton(
                                        "Задача",
                                        on_click=lambda e, i=n.id: link_task(i),
                                    ),
                                    ft.TextButton(
                                        "Связь",
                                        on_click=lambda e, i=n.id: start_edge(i),
                                    ),
                                    ft.IconButton(
                                        icon=ft.Icons.DELETE_OUTLINE,
                                        icon_size=16,
                                        icon_color=RED,
                                        tooltip="Удалить",
                                        on_click=lambda e, i=n.id: delete_node(i),
                                    ),
                                ],
                                spacing=0,
                                wrap=True,
                                run_spacing=0,
                            ),
                        ],
                        spacing=4,
                    ),
                    padding=10,
                    **card_style(accent=selected),
                )
            )

        def delete_edge(eid: int, from_title: str, to_title: str):
            def yes():
                with get_session() as session:
                    roadmap_service.delete_edge(session, eid)
                show_snack(page, "Связь удалена")
                paint()

            confirm_delete(
                page,
                title="Удалить связь?",
                message=f"«{from_title}» → «{to_title}» будет удалена.",
                on_confirm=yes,
            )

        edge_rows = []
        for edge in edges:
            a = by_id.get(edge.from_node_id)
            b = by_id.get(edge.to_node_id)
            from_t = a.title if a else f"#{edge.from_node_id}"
            to_t = b.title if b else f"#{edge.to_node_id}"
            edge_rows.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.TIMELINE, color=ORANGE, size=16),
                            ft.Text(
                                f"{from_t} → {to_t}",
                                size=13,
                                color=TEXT,
                                expand=True,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE,
                                icon_size=16,
                                icon_color=RED,
                                tooltip="Удалить связь",
                                on_click=lambda e, i=edge.id, ftit=from_t, ttit=to_t: delete_edge(
                                    i, ftit, ttit
                                ),
                            ),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=10,
                    **card_style(),
                )
            )

        def _legend(label: str, color: str) -> ft.Control:
            return ft.Row(
                [
                    ft.Container(width=10, height=10, bgcolor=color, border_radius=5),
                    ft.Text(label, size=11, color=MUTED),
                ],
                spacing=6,
                tight=True,
            )

        canvas_host.content = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(
                            "Карта",
                            size=26,
                            weight=ft.FontWeight.W_700,
                            color=TEXT,
                            expand=True,
                        ),
                        muted(f"{len(nodes)} узлов · {len(edges)} связей"),
                    ]
                ),
                muted("Канва зависимостей · нажмите кнопки под узлами"),
                ft.Row(
                    [
                        _legend("Готово", GREEN),
                        _legend("Активен", ORANGE),
                        _legend("Ожидает", MUTED),
                    ],
                    spacing=14,
                ),
                ft.Row(
                    [
                        ft.Container(
                            content=ft.Text(
                                "+ Узел",
                                size=12,
                                weight=ft.FontWeight.W_600,
                                color="#0F0F12",
                            ),
                            bgcolor=ORANGE,
                            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
                            border_radius=ft.BorderRadius.all(14),
                            on_click=add_node,
                            ink=True,
                        ),
                        ft.Container(
                            content=ft.Text("Ребро", size=12, color=TEXT),
                            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
                            border_radius=ft.BorderRadius.all(14),
                            border=ft.Border.all(1, BORDER),
                            on_click=toolbar_edge,
                            ink=True,
                        ),
                        ft.Container(
                            content=ft.Text("Авто-раскладка", size=12, color=TEXT),
                            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
                            border_radius=ft.BorderRadius.all(14),
                            border=ft.Border.all(1, BORDER),
                            on_click=auto_layout,
                            ink=True,
                        ),
                    ],
                    spacing=8,
                ),
                ft.Container(
                    content=ft.Row([canvas], scroll=ft.ScrollMode.AUTO),
                    padding=8,
                    **card_style(),
                    height=380,
                ),
                ft.Text("Узлы", size=16, weight=ft.FontWeight.W_600, color=TEXT),
                *(node_rows or [empty_state("Нет узлов", "Добавьте первый узел", emoji="🗺️")]),
                ft.Text("Связи", size=16, weight=ft.FontWeight.W_600, color=TEXT),
                *(edge_rows or [empty_state("Нет связей", "Нажмите «Связь» на узле", emoji="🔗")]),
                ft.Container(height=8),
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
        page.update()

    paint()
    return ft.Container(
        content=canvas_host,
        padding=ft.Padding.only(left=16, right=16, top=18, bottom=8),
        expand=True,
    )
