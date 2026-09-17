"""Shared confirm / snack helpers."""
from __future__ import annotations

import flet as ft

from app.ui.theme import ORANGE, RED, TEXT


def show_snack(
    page: ft.Page,
    message: str,
    *,
    error: bool = False,
    action_label: str | None = None,
    on_action=None,
    duration_ms: int | None = None,
) -> None:
    """Show a SnackBar; optional action (e.g. «Отменить») and custom duration."""
    action = None
    if action_label and callable(on_action):
        action = ft.SnackBarAction(
            label=action_label,
            text_color="#0F0F12" if not error else TEXT,
            on_click=lambda e: on_action(),
        )
    kwargs: dict = {
        "bgcolor": RED if error else ORANGE,
        "action": action,
    }
    if duration_ms is not None:
        kwargs["duration"] = ft.Duration(milliseconds=int(duration_ms))
    page.show_dialog(
        ft.SnackBar(
            ft.Text(message, color="#0F0F12" if not error else TEXT),
            **kwargs,
        )
    )


def confirm_delete(
    page: ft.Page,
    *,
    title: str = "Удалить?",
    message: str = "Действие нельзя отменить.",
    on_confirm,
    confirm_label: str = "Удалить",
) -> None:
    def _yes(_):
        page.pop_dialog()
        on_confirm()

    page.show_dialog(
        ft.AlertDialog(
            title=ft.Text(title, color=TEXT),
            content=ft.Text(message, color=TEXT),
            actions=[
                ft.TextButton("Отмена", on_click=lambda e: page.pop_dialog()),
                ft.TextButton(confirm_label, on_click=_yes, style=ft.ButtonStyle(color=RED)),
            ],
        )
    )


def pick_date(
    page: ft.Page,
    *,
    value=None,
    on_picked,
    help_text: str = "Выберите дату",
) -> None:
    """Open Flet DatePicker; call on_picked(date|None)."""

    def _changed(e):
        page.pop_dialog()
        picked = e.control.value
        if picked is not None:
            # DatePicker may return datetime
            if hasattr(picked, "date"):
                picked = picked.date()
            on_picked(picked)

    dp = ft.DatePicker(
        value=value,
        help_text=help_text,
        cancel_text="Отмена",
        confirm_text="Выбрать",
        on_change=_changed,
    )
    page.show_dialog(dp)
