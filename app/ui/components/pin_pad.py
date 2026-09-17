"""iOS-style PIN dots + numeric keypad (shared by lock and PIN setup)."""
from __future__ import annotations

import flet as ft

from app.ui.theme import BORDER, CARD, MUTED, ORANGE, RED, TEXT


def build_pin_dots(
    filled: int,
    *,
    total: int = 4,
    error: bool = False,
    shake: bool = False,
) -> ft.Control:
    color = RED if error else ORANGE
    empty = RED if error else BORDER
    dots = []
    n = max(0, min(int(filled), total))
    for i in range(total):
        on = i < n
        dots.append(
            ft.Container(
                width=14,
                height=14,
                border_radius=ft.BorderRadius.all(7),
                bgcolor=color if on else "transparent",
                border=ft.Border.all(2, color if on else empty),
            )
        )
    row = ft.Row(
        dots,
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=16,
    )
    return ft.Container(
        content=row,
        offset=ft.Offset(0.04, 0) if shake else ft.Offset(0, 0),
        animate_offset=ft.Animation(90, ft.AnimationCurve.EASE_IN_OUT),
        alignment=ft.Alignment.CENTER,
        height=28,
    )


def build_number_pad(
    *,
    on_digit,
    on_backspace,
    disabled: bool = False,
) -> ft.Control:
    def key(label: str, *, on_click, muted: bool = False) -> ft.Control:
        return ft.Container(
            content=ft.Text(
                label,
                size=22 if label.isdigit() else 18,
                weight=ft.FontWeight.W_600,
                color=MUTED if disabled or muted else TEXT,
            ),
            width=74,
            height=74,
            bgcolor=CARD,
            border=ft.Border.all(1, BORDER),
            border_radius=ft.BorderRadius.all(37),
            alignment=ft.Alignment.CENTER,
            on_click=None if disabled else on_click,
            ink=not disabled,
            opacity=0.45 if disabled else 1.0,
        )

    rows: list[ft.Control] = []
    layout = [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"]]
    for line in layout:
        rows.append(
            ft.Row(
                [
                    key(d, on_click=lambda e, digit=d: on_digit(digit))
                    for d in line
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=16,
            )
        )
    rows.append(
        ft.Row(
            [
                ft.Container(width=74, height=74),
                key("0", on_click=lambda e: on_digit("0")),
                key("⌫", on_click=lambda e: on_backspace(), muted=True),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=16,
        )
    )
    return ft.Column(rows, spacing=12, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
