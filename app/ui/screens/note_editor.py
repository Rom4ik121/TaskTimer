"""Markdown note editor — Preview (ft.Markdown GFM) / Edit toggle."""
from __future__ import annotations

import flet as ft
from pydantic import ValidationError

from app.schemas import NoteWrite
from app.services import notes_service
from app.ui.components.dialogs import ru_validation_message, show_toast, validation_fail
from app.ui.haptics import haptic
from app.ui.theme import BG, BORDER, CARD, MUTED, ORANGE, TEXT, muted


def build_note_editor(
    page: ft.Page,
    *,
    filename: str,
    on_back,
    refresh_all=None,
    title_override: str | None = None,
) -> ft.Control:
    """Full-screen note: Preview ↔ Edit with GFM Markdown."""
    notes_service.ensure_vault()
    try:
        safe = notes_service.sanitize_filename(filename)
    except ValueError:
        safe = "home.md"

    state = {
        "mode": "preview",  # preview | edit
        "filename": safe,
        "dirty": False,
        "content": notes_service.read_note(safe),
    }

    host = ft.Container(expand=True)
    def _md_control(value: str) -> ft.Control:
        ext = ft.MarkdownExtensionSet.GITHUB_FLAVORED
        return ft.Markdown(
            value or "_Пустая заметка_",
            selectable=True,
            extension_set=ext,
            auto_follow_links=True,
            on_tap_link=lambda e: _on_link(e.data or ""),
            shrink_wrap=True,
        )

    def _on_link(url: str):
        u = (url or "").strip()
        if not u:
            return
        # In-vault relative .md links
        if u.endswith(".md") and "://" not in u and not u.startswith("/"):
            try:
                name = notes_service.sanitize_filename(u)
            except ValueError:
                show_toast(page, "Небезопасная ссылка", kind="error")
                return
            if notes_service.note_exists(name):
                state["filename"] = name
                state["content"] = notes_service.read_note(name)
                state["dirty"] = False
                state["mode"] = "preview"
                paint()
                return
            show_toast(page, f"Нет файла {name}", kind="error")
            return
        # External — open if page supports
        try:
            page.launch_url(u)
        except Exception:
            show_toast(page, u[:80], kind="info")

    def save():
        if not (state["filename"] or "").strip():
            validation_fail(page, "Укажите имя файла .md")
            return
        try:
            data = NoteWrite(filename=state["filename"], content=state["content"] or "")
        except ValidationError as exc:
            validation_fail(page, ru_validation_message(exc, fallback="Не удалось сохранить заметку"))
            return
        notes_service.write_note(data.filename, data.content)
        state["dirty"] = False
        haptic(page, "success")
        show_toast(page, "Сохранено", kind="success")
        # Local paint only — avoid full-app remount that would drop edit mode.
        paint()

    def _on_edit(e):
        state["content"] = e.control.value or ""
        state["dirty"] = True

    def paint():
        mode = state["mode"]
        content = state["content"] or ""
        fname = state["filename"]
        display_title = title_override if (
            title_override and fname == safe
        ) else fname.replace(".md", "")

        editor = ft.TextField(
            value=content,
            multiline=True,
            min_lines=18,
            max_lines=28,
            border_color=BORDER,
            focused_border_color=ORANGE,
            color=TEXT,
            bgcolor=CARD,
            text_size=14,
            expand=True,
            on_change=lambda e: _on_edit(e),
        )

        preview = ft.Container(
            content=_md_control(content),
            padding=14,
            bgcolor=CARD,
            border=ft.Border.all(1, BORDER),
            border_radius=ft.BorderRadius.all(14),
            expand=True,
        )

        def set_mode(m: str):
            if mode == "edit" and m == "preview":
                # pull latest from field if still mounted
                pass
            state["mode"] = m
            paint()

        toggle = ft.Row(
            [
                ft.Container(
                    content=ft.Text(
                        "Просмотр",
                        size=12,
                        weight=ft.FontWeight.W_600,
                        color="#0F0F12" if mode == "preview" else MUTED,
                    ),
                    bgcolor=ORANGE if mode == "preview" else "transparent",
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                    border_radius=ft.BorderRadius.all(10),
                    border=ft.Border.all(1, ORANGE if mode == "preview" else BORDER),
                    on_click=lambda e: set_mode("preview"),
                    ink=True,
                ),
                ft.Container(
                    content=ft.Text(
                        "Правка",
                        size=12,
                        weight=ft.FontWeight.W_600,
                        color="#0F0F12" if mode == "edit" else MUTED,
                    ),
                    bgcolor=ORANGE if mode == "edit" else "transparent",
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                    border_radius=ft.BorderRadius.all(10),
                    border=ft.Border.all(1, ORANGE if mode == "edit" else BORDER),
                    on_click=lambda e: set_mode("edit"),
                    ink=True,
                ),
                ft.Container(expand=True),
                ft.Container(
                    content=ft.Text(
                        "Сохранить",
                        size=12,
                        weight=ft.FontWeight.W_700,
                        color="#0F0F12",
                    ),
                    bgcolor=ORANGE,
                    padding=ft.Padding.symmetric(horizontal=14, vertical=8),
                    border_radius=ft.BorderRadius.all(10),
                    on_click=lambda e: save(),
                    ink=True,
                    opacity=1.0 if state["dirty"] or mode == "edit" else 0.7,
                ),
            ],
            spacing=8,
        )

        body = editor if mode == "edit" else preview

        host.content = ft.Column(
            [
                ft.Row(
                    [
                        ft.IconButton(
                            icon=ft.Icons.ARROW_BACK_IOS_NEW,
                            icon_color=TEXT,
                            icon_size=18,
                            on_click=lambda e: on_back(),
                        ),
                        ft.Column(
                            [
                                ft.Text(
                                    display_title,
                                    size=20,
                                    weight=ft.FontWeight.W_700,
                                    color=TEXT,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                                muted(fname + (" · изменено" if state["dirty"] else "")),
                            ],
                            spacing=0,
                            expand=True,
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                toggle,
                muted("Markdown · GFM · ссылки .md открываются в vault"),
                ft.Container(content=body, expand=True),
            ],
            spacing=10,
            expand=True,
        )
        page.update()

    paint()
    return ft.Container(
        content=host,
        padding=ft.Padding.only(left=16, right=16, top=12, bottom=8),
        expand=True,
        bgcolor=BG,
    )
