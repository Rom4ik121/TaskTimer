"""Bottom navigation bar."""
from __future__ import annotations

import flet as ft

from app.ui.theme import BG_ELEVATED, ORANGE


def build_nav(
    selected: int,
    on_change,
    *,
    tasks_badge: int | None = None,
) -> ft.NavigationBar:
    """Build bottom nav. Optional ``tasks_badge`` = active (non-done) task count."""
    badge: str | ft.Badge | None = None
    if tasks_badge is not None and int(tasks_badge) > 0:
        n = int(tasks_badge)
        label = str(n) if n < 100 else "99+"
        badge = ft.Badge(
            label=label,
            bgcolor=ORANGE,
            text_color="#0F0F12",
            small_size=8,
            large_size=16,
        )

    return ft.NavigationBar(
        selected_index=selected,
        bgcolor=BG_ELEVATED,
        indicator_color="#FF8A0033",
        label_behavior=ft.NavigationBarLabelBehavior.ALWAYS_SHOW,
        on_change=on_change,
        destinations=[
            ft.NavigationBarDestination(
                icon=ft.Icons.HOME_OUTLINED,
                selected_icon=ft.Icons.HOME_ROUNDED,
                label="Дом",
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.CHECK_CIRCLE_OUTLINE,
                selected_icon=ft.Icons.CHECK_CIRCLE,
                label="Задачи",
                badge=badge,
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.GRID_VIEW_OUTLINED,
                selected_icon=ft.Icons.GRID_VIEW_ROUNDED,
                label="Холст",
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.ANALYTICS_OUTLINED,
                selected_icon=ft.Icons.ANALYTICS,
                label="Статы",
            ),
        ],
    )
