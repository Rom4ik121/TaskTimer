"""Brief skippable first-launch splash — icon + TaskTimer."""
from __future__ import annotations

import asyncio

import flet as ft

from app.ui.motion import splash_fade
from app.ui.theme import BG, MUTED, ORANGE, TEXT, icon_src


def build_splash(
    page: ft.Page,
    *,
    on_done,
    auto_ms: int = 800,
    skippable: bool = True,
) -> ft.Control:
    """Show brand mark ~0.6–1s; tap anywhere to skip. ``on_done`` is called once.

    ``auto_ms <= 0`` disables the timer (idle brand panel under onboarding).
    """
    state = {"done": False}

    def finish(_e=None) -> None:
        if state["done"]:
            return
        if not skippable and _e is not None:
            return
        state["done"] = True
        on_done()

    async def wait_then_finish() -> None:
        await asyncio.sleep(max(0.4, auto_ms / 1000.0))
        finish()

    if auto_ms > 0:
        try:
            page.run_task(wait_then_finish)
        except Exception:
            pass

    icon = ft.Image(
        src=icon_src(small=True),
        width=96,
        height=96,
        fit=ft.BoxFit.CONTAIN,
    )
    root = ft.Container(
        content=ft.Column(
            [
                ft.Container(expand=True),
                icon,
                ft.Container(height=16),
                ft.Text(
                    "TaskTimer",
                    size=28,
                    weight=ft.FontWeight.W_700,
                    color=TEXT,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=8),
                ft.Text(
                    "коснитесь, чтобы продолжить",
                    size=12,
                    color=MUTED,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(expand=True),
                ft.Container(
                    width=36,
                    height=4,
                    bgcolor=ORANGE,
                    border_radius=ft.BorderRadius.all(2),
                ),
                ft.Container(height=28),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
            expand=True,
        ),
        bgcolor=BG,
        expand=True,
        on_click=finish if skippable else None,
        ink=False,
    )
    return splash_fade(root, page)
