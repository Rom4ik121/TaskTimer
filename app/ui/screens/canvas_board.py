"""Infinite Obsidian-style canvas — pan/zoom, section MD nodes, note nodes, roadmap layer."""
from __future__ import annotations

import flet as ft
import flet.canvas as cv

from app.db import get_session
from app.schemas import CanvasNodeCreate
from app.services import canvas_service, notes_service, roadmap_service
from app.ui.components.dialogs import (
    confirm_delete,
    set_field_error,
    show_info,
    show_toast,
    validation_fail,
)
from app.ui.theme import (
    BG,
    BORDER,
    CARD,
    GREEN,
    MUTED,
    ORANGE,
    ORANGE_SOFT,
    TEXT,
    muted,
    screen_header,
    screen_insets,
)

WORLD_W = 2400.0
WORLD_H = 1600.0
GRID = 48


def build_canvas_board(
    page: ft.Page,
    *,
    refresh_all=None,
    on_open_note=None,
) -> ft.Control:
    """Bottom-nav «Холст»: InteractiveViewer + section/note cards + optional roadmap."""
    host = ft.Container(expand=True)
    state = {
        "show_roadmap": False,
        "pick_edge_from": None,
        "framed": False,
    }

    def open_note(filename: str, title: str | None = None):
        if on_open_note:
            on_open_note(filename, title)
        else:
            show_toast(page, f"Заметка: {filename}", kind="info")

    def paint():
        notes_service.ensure_vault()
        with get_session() as session:
            canvas_service.ensure_canvas_seeded(session)
            nodes = canvas_service.list_nodes(session)
            edges = canvas_service.list_edges(session)
            rm_nodes = roadmap_service.list_nodes(session) if state["show_roadmap"] else []
            rm_edges = roadmap_service.list_edges(session) if state["show_roadmap"] else []

        by_id = {n.id: n for n in nodes}

        # --- Grid background via canvas shapes ---
        grid_shapes: list[cv.Shape] = []
        grid_color = "#1A1A22"
        accent_grid = "#2A2018"
        for x in range(0, int(WORLD_W) + 1, GRID):
            col = accent_grid if x % (GRID * 5) == 0 else grid_color
            grid_shapes.append(
                cv.Line(x, 0, x, WORLD_H, paint=ft.Paint(color=col, stroke_width=1))
            )
        for y in range(0, int(WORLD_H) + 1, GRID):
            col = accent_grid if y % (GRID * 5) == 0 else grid_color
            grid_shapes.append(
                cv.Line(0, y, WORLD_W, y, paint=ft.Paint(color=col, stroke_width=1))
            )

        # Canvas edges (between note/section nodes)
        for edge in edges:
            a = by_id.get(edge.from_node_id)
            b = by_id.get(edge.to_node_id)
            if not a or not b:
                continue
            ax = a.x + (a.w or 160) / 2
            ay = a.y + (a.h or 72) / 2
            bx = b.x + (b.w or 160) / 2
            by = b.y + (b.h or 72) / 2
            grid_shapes.append(
                cv.Line(
                    ax,
                    ay,
                    bx,
                    by,
                    paint=ft.Paint(color="#3A3028", stroke_width=2),
                )
            )

        # Roadmap layer edges (offset into lower-right area)
        RM_OX, RM_OY = 100.0, 700.0
        rm_by = {n.id: n for n in rm_nodes}
        for edge in rm_edges:
            a = rm_by.get(edge.from_node_id)
            b = rm_by.get(edge.to_node_id)
            if not a or not b:
                continue
            grid_shapes.append(
                cv.Line(
                    RM_OX + a.x + 54,
                    RM_OY + a.y + 22,
                    RM_OX + b.x + 54,
                    RM_OY + b.y + 22,
                    paint=ft.Paint(color="#3A3A44", stroke_width=1.5),
                )
            )

        world_canvas = cv.Canvas(
            grid_shapes,
            width=WORLD_W,
            height=WORLD_H,
        )

        def _node_card(n) -> ft.Control:
            kind = n.kind or "note"
            accent = n.color or (ORANGE if kind == "section" else "#4C8DFF")
            w = float(n.w or 160)
            h = float(n.h or 88)
            subtitle = {
                "section": "раздел · .md",
                "note": "заметка",
                "roadmap": "роадмап",
            }.get(kind, kind)
            ref = (n.ref or "").strip()

            def on_tap(_e, node=n):
                r = (node.ref or "").strip()
                if node.kind in ("section", "note") and r:
                    open_note(r, node.title)
                elif node.kind == "roadmap":
                    open_note("roadmap.md", "Роадмап")
                else:
                    show_toast(page, node.title, kind="info")

            return ft.Container(
                left=float(n.x),
                top=float(n.y),
                width=w,
                height=h,
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Container(
                                    width=8,
                                    height=8,
                                    bgcolor=accent,
                                    border_radius=4,
                                ),
                                ft.Text(
                                    n.title[:18],
                                    size=13,
                                    weight=ft.FontWeight.W_700,
                                    color=TEXT,
                                    expand=True,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                            ],
                            spacing=6,
                        ),
                        ft.Text(subtitle, size=10, color=MUTED),
                        ft.Text(
                            ref[:22] if ref else "",
                            size=10,
                            color=ORANGE if kind == "section" else MUTED,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ],
                    spacing=2,
                    tight=True,
                ),
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                bgcolor=CARD,
                border=ft.Border.all(1.5, accent if kind == "section" else BORDER),
                border_radius=ft.BorderRadius.all(14),
                shadow=ft.BoxShadow(
                    blur_radius=16,
                    color="#00000066",
                    offset=ft.Offset(0, 4),
                ),
                on_click=on_tap,
                ink=True,
                tooltip=f"Открыть {ref or n.title}",
            )

        node_controls = [_node_card(n) for n in nodes]

        # Roadmap mirror cards
        STATUS_FILL = {"pending": MUTED, "active": ORANGE, "done": GREEN}
        for rn in rm_nodes:
            fill = STATUS_FILL.get(rn.status, MUTED)

            def _rm_tap(_e, node=rn):
                open_note("roadmap.md", f"Роадмап · {node.title}")

            node_controls.append(
                ft.Container(
                    left=RM_OX + float(rn.x),
                    top=RM_OY + float(rn.y),
                    width=120,
                    height=52,
                    content=ft.Row(
                        [
                            ft.Container(
                                width=8, height=8, bgcolor=fill, border_radius=4
                            ),
                            ft.Text(
                                rn.title[:14],
                                size=11,
                                weight=ft.FontWeight.W_600,
                                color=TEXT,
                                expand=True,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                        ],
                        spacing=6,
                    ),
                    padding=10,
                    bgcolor="#141418",
                    border=ft.Border.all(1, fill if rn.status != "pending" else BORDER),
                    border_radius=ft.BorderRadius.all(12),
                    on_click=_rm_tap,
                    ink=True,
                    tooltip="Узел роадмапа → roadmap.md",
                )
            )

        world = ft.Container(
            width=WORLD_W,
            height=WORLD_H,
            bgcolor="#0C0C10",
            content=ft.Stack(
                [world_canvas, *node_controls],
                width=WORLD_W,
                height=WORLD_H,
            ),
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

        # Cluster sits top-left of WORLD; align TOP_LEFT + mild zoom-out so
        # the 2×3 section cards fit the phone frame on first open.
        viewer = ft.InteractiveViewer(
            content=world,
            pan_enabled=True,
            scale_enabled=True,
            min_scale=0.35,
            max_scale=2.8,
            constrained=False,
            boundary_margin=ft.Margin.all(400),
            trackpad_scroll_causes_scale=True,
            alignment=ft.Alignment.TOP_LEFT,
            expand=True,
        )

        async def _frame_first_open():
            try:
                # Zoom out slightly so ~400×430 cluster fits ~390-wide phone.
                await viewer.zoom(0.88)
            except Exception as exc:
                import sys

                print(f"[TaskTimer] canvas frame: {exc}", file=sys.stderr)

        if not state.get("framed"):
            state["framed"] = True
            try:
                page.run_task(_frame_first_open)
            except Exception:
                pass

        def add_note_node(_):
            title_f = ft.TextField(
                label="Название заметки",
                border_color=BORDER,
                focused_border_color=ORANGE,
                color=TEXT,
            )
            file_f = ft.TextField(
                label="Файл (например ideas.md)",
                value="note.md",
                border_color=BORDER,
                focused_border_color=ORANGE,
                color=TEXT,
            )

            def submit(__):
                set_field_error(title_f, None)
                set_field_error(file_f, None)
                title = (title_f.value or "").strip()
                if not title:
                    validation_fail(page, "Введите название заметки", title_f)
                    return
                raw = (file_f.value or "").strip()
                if not raw:
                    validation_fail(page, "Укажите имя файла .md", file_f)
                    return
                try:
                    fname = notes_service.sanitize_filename(raw)
                except ValueError:
                    validation_fail(page, "Имя файла: только *.md без пути", file_f)
                    return
                if not notes_service.note_exists(fname):
                    try:
                        notes_service.create_note(
                            fname, f"# {title}\n\n"
                        )
                    except FileExistsError:
                        pass
                n_count = len([x for x in nodes if x.kind == "note"])
                nx = 200.0 + (n_count % 4) * 200
                ny = 520.0 + (n_count // 4) * 100
                with get_session() as session:
                    canvas_service.create_node(
                        session,
                        CanvasNodeCreate(
                            title=title,
                            x=nx,
                            y=ny,
                            kind="note",
                            ref=fname,
                            color="#4C8DFF",
                            w=160,
                            h=72,
                        ),
                    )
                page.pop_dialog()
                show_toast(page, f"Узел · {fname}", kind="success")
                paint()

            page.show_dialog(
                ft.AlertDialog(
                    title=ft.Text("Новая заметка на холсте", color=TEXT),
                    content=ft.Column([title_f, file_f], tight=True, height=140, spacing=10),
                    actions=[
                        ft.TextButton("Отмена", on_click=lambda e: page.pop_dialog()),
                        ft.TextButton("Добавить", on_click=submit),
                    ],
                )
            )

        def toggle_roadmap(_):
            state["show_roadmap"] = not state["show_roadmap"]
            show_toast(
                page,
                "Слой роадмапа вкл" if state["show_roadmap"] else "Слой роадмапа выкл",
                kind="info",
            )
            paint()

        def open_section_picker(_):
            # Quick open any section MD
            opts = list(notes_service.SECTION_TITLES_RU.items())

            def make_btn(key: str, label: str):
                fname = notes_service.SECTION_FILES[key]
                return ft.TextButton(
                    label,
                    on_click=lambda e, f=fname, t=label: (
                        page.pop_dialog(),
                        open_note(f, t),
                    ),
                )

            show_info(
                page,
                title="Открыть раздел",
                content=ft.Column(
                    [make_btn(k, v) for k, v in opts],
                    tight=True,
                    spacing=4,
                    height=220,
                    scroll=ft.ScrollMode.AUTO,
                ),
                ok_label="Закрыть",
            )

        def delete_note_node(nid: int):
            def yes():
                with get_session() as session:
                    canvas_service.delete_node(session, nid)
                show_toast(page, "Узел удалён", kind="success")
                paint()

            confirm_delete(
                page,
                title="Удалить узел с холста?",
                message="Файл .md на диске останется.",
                on_confirm=yes,
            )

        # Compact list of free note nodes for manage
        note_rows = []
        for n in nodes:
            if n.kind != "note":
                continue
            note_rows.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text(n.title, size=12, color=TEXT, expand=True),
                            ft.IconButton(
                                icon=ft.Icons.DESCRIPTION_OUTLINED,
                                icon_size=16,
                                icon_color=ORANGE,
                                tooltip="Открыть",
                                on_click=lambda e, r=n.ref, t=n.title: open_note(r, t),
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE,
                                icon_size=16,
                                icon_color="#FF5C5C",
                                tooltip="Убрать с холста",
                                on_click=lambda e, i=n.id: delete_note_node(i),
                            ),
                        ],
                        spacing=0,
                    ),
                    padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                )
            )

        toolbar = ft.Row(
            [
                ft.Container(
                    content=ft.Text(
                        "+ Заметка",
                        size=11,
                        weight=ft.FontWeight.W_700,
                        color="#0F0F12",
                    ),
                    bgcolor=ORANGE,
                    padding=ft.Padding.symmetric(horizontal=10, vertical=7),
                    border_radius=ft.BorderRadius.all(10),
                    on_click=add_note_node,
                    ink=True,
                ),
                ft.Container(
                    content=ft.Text(
                        "Роадмап" if not state["show_roadmap"] else "Скрыть RM",
                        size=11,
                        color=TEXT,
                    ),
                    padding=ft.Padding.symmetric(horizontal=10, vertical=7),
                    border_radius=ft.BorderRadius.all(10),
                    border=ft.Border.all(
                        1, ORANGE if state["show_roadmap"] else BORDER
                    ),
                    bgcolor=ORANGE_SOFT if state["show_roadmap"] else "transparent",
                    on_click=toggle_roadmap,
                    ink=True,
                ),
                ft.Container(
                    content=ft.Text("Разделы", size=11, color=TEXT),
                    padding=ft.Padding.symmetric(horizontal=10, vertical=7),
                    border_radius=ft.BorderRadius.all(10),
                    border=ft.Border.all(1, BORDER),
                    on_click=open_section_picker,
                    ink=True,
                ),
            ],
            spacing=6,
            wrap=True,
            run_spacing=6,
        )

        host.content = ft.Column(
            [
                screen_header(
                    "Холст",
                    subtitle="Щипок / колесо — зум · перетащите фон — пан · тап — MD",
                    actions=[muted(f"{len(nodes)} узлов")],
                ),
                toolbar,
                ft.Container(
                    content=viewer,
                    expand=True,
                    border=ft.Border.all(1, BORDER),
                    border_radius=ft.BorderRadius.all(16),
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                    bgcolor="#0C0C10",
                ),
                *(
                    [
                        muted("Заметки на холсте"),
                        ft.Column(note_rows, spacing=2, tight=True),
                    ]
                    if note_rows
                    else []
                ),
            ],
            spacing=8,
            expand=True,
        )
        page.update()

    paint()
    return ft.Container(
        content=host,
        padding=screen_insets(),
        expand=True,
        bgcolor=BG,
    )
