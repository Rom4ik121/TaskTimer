"""Reusable filter BottomSheet — sections + Сбросить / Готово."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import flet as ft

from app.ui.haptics import haptic
from app.ui.motion import open_sheet_motion, pulse_press, sheet_motion_wrap
from app.ui.theme import BG, BORDER, CARD, MUTED, ORANGE, TEXT, muted


@dataclass
class FilterSection:
    key: str
    title: str
    options: list[tuple[str, Any]]
    value: Any = None
    accents: dict[Any, str] = field(default_factory=dict)


def choice_chip(
    label: str,
    *,
    active: bool,
    accent: str = ORANGE,
    on_click=None,
    page: ft.Page | None = None,
) -> ft.Container:
    chip = ft.Container(
        content=ft.Text(
            label,
            size=12,
            color=BG if active else MUTED,
            weight=ft.FontWeight.W_500,
        ),
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        border_radius=ft.BorderRadius.all(16),
        bgcolor=accent if active else "transparent",
        border=ft.Border.all(1, accent if active else BORDER),
        ink=True,
    )

    def _on(e):
        pulse_press(chip)
        haptic(page, "selection", control=chip)
        if callable(on_click):
            on_click(e)

    chip.on_click = _on
    return chip


def _paint_chip(chip: ft.Container, *, active: bool, accent: str) -> None:
    chip.bgcolor = accent if active else "transparent"
    chip.border = ft.Border.all(1, accent if active else BORDER)
    content = getattr(chip, "content", None)
    if content is not None and hasattr(content, "color"):
        content.color = BG if active else MUTED


def show_filter_sheet(
    page: ft.Page,
    *,
    title: str = "Фильтры",
    sections: list[FilterSection],
    on_apply: Callable[[dict[str, Any]], None],
    reset_values: dict[str, Any] | None = None,
) -> None:
    """Open a scrollable BottomSheet. Dismiss without Готово keeps live filters."""
    draft: dict[str, Any] = {s.key: s.value for s in sections}
    chip_map: dict[str, list[tuple[Any, ft.Container]]] = {}
    hosts: dict[str, ft.Control] = {}

    def _accent(section: FilterSection, key: Any) -> str:
        return section.accents.get(key, ORANGE)

    def _paint_section(section: FilterSection) -> None:
        current = draft.get(section.key)
        for key, chip in chip_map.get(section.key, []):
            _paint_chip(chip, active=current == key, accent=_accent(section, key))

    def _set(section: FilterSection, key: Any):
        def _inner(_e=None):
            draft[section.key] = key
            _paint_section(section)
            try:
                page.update()
            except Exception:
                pass

        return _inner

    def _rebuild_section_row(section: FilterSection) -> ft.Row:
        chips: list[ft.Container] = []
        pairs: list[tuple[Any, ft.Container]] = []
        current = draft.get(section.key)
        for label, key in section.options:
            chip = choice_chip(
                label,
                active=current == key,
                accent=_accent(section, key),
                on_click=_set(section, key),
                page=page,
            )
            chips.append(chip)
            pairs.append((key, chip))
        chip_map[section.key] = pairs
        return ft.Row(chips, spacing=8, run_spacing=8, wrap=True)

    body_controls: list[ft.Control] = [
        ft.Text(title, size=20, weight=ft.FontWeight.W_700, color=TEXT),
        muted("Выберите условия, затем «Готово»"),
    ]
    for section in sections:
        row = _rebuild_section_row(section)
        hosts[section.key] = row
        body_controls.extend(
            [
                ft.Container(height=8),
                muted(section.title),
                row,
            ]
        )

    def do_reset(_e=None):
        haptic(page, "light")
        zeros = reset_values if reset_values is not None else {s.key: None for s in sections}
        for section in sections:
            draft[section.key] = zeros.get(section.key)
            _paint_section(section)
        try:
            page.update()
        except Exception:
            pass

    def do_apply(_e=None):
        haptic(page, "selection")
        try:
            page.pop_dialog()
        except Exception:
            pass
        on_apply(dict(draft))

    def do_dismiss(_e=None):
        try:
            page.pop_dialog()
        except Exception:
            pass

    reset_btn = ft.Container(
        content=ft.Text("Сбросить", size=14, weight=ft.FontWeight.W_600, color=TEXT),
        padding=ft.Padding.symmetric(horizontal=18, vertical=12),
        border=ft.Border.all(1, BORDER),
        border_radius=ft.BorderRadius.all(14),
        on_click=do_reset,
        ink=True,
        expand=True,
        alignment=ft.Alignment.CENTER,
    )
    done_btn = ft.Container(
        content=ft.Text("Готово", size=14, weight=ft.FontWeight.W_700, color=BG),
        padding=ft.Padding.symmetric(horizontal=18, vertical=12),
        bgcolor=ORANGE,
        border_radius=ft.BorderRadius.all(14),
        on_click=do_apply,
        ink=True,
        expand=True,
        alignment=ft.Alignment.CENTER,
    )

    inner = ft.Column(
        [
            *body_controls,
            ft.Container(height=12),
            ft.Row([reset_btn, done_btn], spacing=10),
        ],
        spacing=8,
        scroll=ft.ScrollMode.AUTO,
        tight=True,
    )
    try:
        h = float(getattr(page, "height", None) or 0)
    except (TypeError, ValueError):
        h = 0.0
    max_h = int(h * 0.82) if h > 200 else 560
    card = ft.Container(
        content=inner,
        padding=ft.Padding.only(left=16, right=16, top=8, bottom=18),
        bgcolor=CARD,
        height=max_h,
    )
    wrap = sheet_motion_wrap(card)
    try:
        sheet = ft.BottomSheet(
            content=wrap,
            bgcolor=CARD,
            dismissible=True,
            draggable=True,
            show_drag_handle=True,
            scrollable=True,
            fullscreen=True,
            on_dismiss=lambda e: None,
        )
    except TypeError:
        sheet = ft.BottomSheet(
            content=wrap,
            bgcolor=CARD,
            dismissible=True,
        )
    page.show_dialog(sheet)
    open_sheet_motion(wrap, page)


def summary_chip(
    text: str,
    *,
    on_click=None,
    page: ft.Page | None = None,
) -> ft.Container:
    """Compact active-filter chip for the main surface."""
    chip = ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.FILTER_ALT, size=14, color=ORANGE),
                ft.Text(
                    text,
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
        padding=ft.Padding.symmetric(horizontal=12, vertical=7),
        border_radius=ft.BorderRadius.all(16),
        bgcolor="#FF8A0018",
        border=ft.Border.all(1, ORANGE),
        on_click=on_click,
        ink=True,
        visible=bool(text),
    )

    def _on(e):
        pulse_press(chip)
        haptic(page, "selection", control=chip)
        if callable(on_click):
            on_click(e)

    chip.on_click = _on
    return chip
