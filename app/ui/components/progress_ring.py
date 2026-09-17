"""Circular / donut progress helpers."""
from __future__ import annotations

import flet as ft
import flet_charts as fc

from app.ui.theme import BG, CARD, GREEN, MUTED, ORANGE, TEXT


def donut_progress(
    percent: float,
    *,
    size: float = 120,
    thickness: float = 14,
    color: str = ORANGE,
    center_label: str | None = None,
    subtitle: str | None = None,
) -> ft.Control:
    pct = max(0.0, min(100.0, percent))
    remain = max(0.001, 100.0 - pct)
    center_r = (size / 2) - thickness - 2
    chart = fc.PieChart(
        sections=[
            fc.PieChartSection(value=max(pct, 0.001), color=color, radius=thickness, title=""),
            fc.PieChartSection(value=remain, color="#2A2A32", radius=thickness, title=""),
        ],
        sections_space=0,
        center_space_color=CARD,
        center_space_radius=center_r,
        width=size,
        height=size,
    )
    label = center_label if center_label is not None else f"{pct:.0f}%"
    stack_controls: list[ft.Control] = [
        chart,
        ft.Container(
            content=ft.Column(
                [
                    ft.Text(label, size=18, weight=ft.FontWeight.W_700, color=TEXT),
                    *([ft.Text(subtitle, size=10, color=MUTED)] if subtitle else []),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=2,
                tight=True,
            ),
            alignment=ft.Alignment.CENTER,
            width=size,
            height=size,
        ),
    ]
    return ft.Stack(stack_controls, width=size, height=size)


def mini_ring(percent: float, color: str = GREEN, size: float = 42) -> ft.Control:
    return ft.ProgressRing(
        value=max(0.0, min(1.0, percent / 100.0)),
        width=size,
        height=size,
        stroke_width=4,
        color=color,
        bgcolor="#2A2A32",
    )
