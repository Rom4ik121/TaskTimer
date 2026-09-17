"""First-run onboarding BottomSheet — 3 RU cards, once via app_meta.onboarded."""
from __future__ import annotations

import flet as ft

from app.db import get_session
from app.services import settings_service
from app.ui import theme as theme_mod
from app.ui.theme import BG, BORDER, CARD, MUTED, TEXT


CARDS: list[dict] = [
    {
        "icon": ft.Icons.FLAG_OUTLINED,
        "title": "Цели с квотой",
        "body": "Ставьте цели и дневную квоту. Логируйте прогресс — серия 🔥 "
        "и календарь покажут, как держите ритм.",
    },
    {
        "icon": ft.Icons.TIMER_OUTLINED,
        "title": "Фокус-таймер",
        "body": "Pomodoro прямо в приложении: работа / перерыв из Настроек, "
        "сессии сохраняются и видны в Статах.",
    },
    {
        "icon": ft.Icons.GRID_VIEW_OUTLINED,
        "title": "Холст и заметки",
        "body": "Бесконечный холст с разделами и Markdown-vault (как Obsidian). "
        "Тап по карточке — откроет .md; иконка заметки есть на Доме и в экранах.",
    },
]


def is_onboarded() -> bool:
    with get_session() as session:
        return settings_service.is_onboarded(session)


def mark_onboarded() -> None:
    with get_session() as session:
        settings_service.mark_onboarded(session)


def clear_onboarded() -> None:
    """Reset first-run flag so Home / Settings can show the sheet again."""
    with get_session() as session:
        settings_service.clear_onboarded(session)


def maybe_show_onboarding(page: ft.Page) -> None:
    """Show BottomSheet once if app_meta.onboarded is not set."""
    if is_onboarded():
        return
    show_onboarding(page)


def show_onboarding(page: ft.Page, *, force: bool = False) -> None:
    """Present 3-card onboarding sheet. Skip / last Далее → mark onboarded.

    Uses the live accent (theme.ORANGE) so Settings presets apply immediately.
    """
    if not force and is_onboarded():
        return

    accent = theme_mod.ORANGE
    accent_soft = getattr(theme_mod, "ORANGE_SOFT", accent + "33")

    state = {"idx": 0}
    icon = ft.Icon(CARDS[0]["icon"], color=accent, size=32)
    icon_wrap = ft.Container(
        content=icon,
        width=64,
        height=64,
        bgcolor=accent_soft,
        border=ft.Border.all(1, accent),
        border_radius=ft.BorderRadius.all(20),
        alignment=ft.Alignment.CENTER,
    )
    title = ft.Text(CARDS[0]["title"], size=22, weight=ft.FontWeight.W_700, color=TEXT)
    body = ft.Text(CARDS[0]["body"], size=14, color=MUTED)
    dots = ft.Row(spacing=6, alignment=ft.MainAxisAlignment.CENTER)
    next_label = ft.Text(
        "Далее", size=15, weight=ft.FontWeight.W_700, color=BG
    )
    next_btn = ft.Container(
        content=next_label,
        bgcolor=accent,
        padding=14,
        border_radius=ft.BorderRadius.all(14),
        alignment=ft.Alignment.CENTER,
        expand=True,
        ink=True,
    )

    def _paint_dots() -> None:
        dots.controls.clear()
        for i in range(len(CARDS)):
            dots.controls.append(
                ft.Container(
                    width=8 if i != state["idx"] else 18,
                    height=8,
                    border_radius=ft.BorderRadius.all(4),
                    bgcolor=accent if i == state["idx"] else BORDER,
                )
            )

    def _apply_card() -> None:
        c = CARDS[state["idx"]]
        icon.name = c["icon"]
        icon.color = accent
        title.value = c["title"]
        body.value = c["body"]
        next_label.value = "Готово" if state["idx"] >= len(CARDS) - 1 else "Далее"
        _paint_dots()
        page.update()

    def _finish() -> None:
        mark_onboarded()
        try:
            page.pop_dialog()
        except Exception:
            pass

    def on_skip(_=None) -> None:
        _finish()

    def on_next(_=None) -> None:
        if state["idx"] >= len(CARDS) - 1:
            _finish()
            return
        state["idx"] += 1
        _apply_card()

    next_btn.on_click = on_next
    _paint_dots()

    card = ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(
                            "TaskTimer",
                            size=13,
                            color=accent,
                            weight=ft.FontWeight.W_600,
                        ),
                        ft.Container(expand=True),
                        ft.TextButton(
                            "Пропустить",
                            on_click=on_skip,
                            style=ft.ButtonStyle(color=accent),
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(height=8),
                ft.Container(
                    content=ft.Column(
                        [
                            icon_wrap,
                            ft.Container(height=10),
                            title,
                            ft.Container(height=6),
                            body,
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.START,
                        spacing=0,
                    ),
                    padding=16,
                    bgcolor=CARD,
                    border_radius=ft.BorderRadius.all(14),
                    border=ft.Border.all(1, accent),
                ),
                ft.Container(height=12),
                dots,
                ft.Container(height=8),
                ft.Row([next_btn], alignment=ft.MainAxisAlignment.CENTER),
            ],
            spacing=0,
            tight=True,
        ),
        padding=ft.Padding.only(left=16, right=16, top=8, bottom=20),
        bgcolor=CARD,
    )

    sheet = ft.BottomSheet(
        content=card,
        bgcolor=CARD,
        dismissible=False,
        draggable=False,
        show_drag_handle=True,
        on_dismiss=lambda e: mark_onboarded(),
    )
    page.show_dialog(sheet)
