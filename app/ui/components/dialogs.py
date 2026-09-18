"""Shared toasts, info/confirm modals, and form validation helpers."""
from __future__ import annotations

from typing import Literal

import flet as ft
from pydantic import ValidationError

from app.ui.motion import DURATION_FAST, anim
from app.ui.haptics import haptic
from app.ui.theme import BORDER, GREEN, ORANGE, RED, TEXT


ToastKind = Literal["success", "error", "info", "warning"]

# Brand charcoal text on warm/success/warning fills; light text on error red.
_TOAST_BG: dict[ToastKind, str] = {
    "success": GREEN,
    "error": RED,
    "info": ORANGE,
    "warning": "#F5C542",
}
_TOAST_FG: dict[ToastKind, str] = {
    "success": "#0F0F12",
    "error": TEXT,
    "info": "#0F0F12",
    "warning": "#0F0F12",
}
_TOAST_MS: dict[ToastKind, int] = {
    "success": 2800,
    "error": 4200,
    "info": 3200,
    "warning": 4000,
}

_RU_BY_LOC = {
    "title": "Введите название",
    "filename": "Укажите имя файла .md",
    "target_value": "Цель должна быть числом больше 0",
    "daily_quota": "Квота должна быть числом больше 0",
    "estimated_min": "Оценка — целое число минут (0–1440)",
    "amount": "Сумма должна быть больше 0",
    "content": "Проверьте текст заметки",
    "display_name": "Укажите имя",
    "accent_hex": "Цвет акцента — HEX, например #FF8A00",
    "unit": "Укажите единицу измерения",
    "ref": "Укажите имя файла .md",
}


def show_toast(
    page: ft.Page,
    message: str,
    *,
    kind: ToastKind = "info",
    action_label: str | None = None,
    on_action=None,
    duration_ms: int | None = None,
) -> None:
    """Toast: success / error / info / warning. Optional undo action."""
    if kind not in _TOAST_BG:
        kind = "info"
    bg = _TOAST_BG[kind]
    fg = _TOAST_FG[kind]
    ms = duration_ms if duration_ms is not None else _TOAST_MS[kind]
    action = None
    if action_label and callable(on_action):
        action = ft.SnackBarAction(
            label=action_label,
            text_color=fg,
            on_click=lambda e: on_action(),
        )
    kwargs: dict = {
        "bgcolor": bg,
        "action": action,
        "duration": ft.Duration(milliseconds=int(ms)),
    }
    body = ft.Container(
        content=ft.Text(message, color=fg),
        opacity=0.0,
        animate_opacity=anim(DURATION_FAST),
    )
    page.show_dialog(
        ft.SnackBar(
            body,
            **kwargs,
        )
    )
    try:
        body.opacity = 1.0
    except Exception:
        pass


def show_snack(
    page: ft.Page,
    message: str,
    *,
    error: bool = False,
    action_label: str | None = None,
    on_action=None,
    duration_ms: int | None = None,
) -> None:
    """Backward-compatible snack → toast (error or success)."""
    show_toast(
        page,
        message,
        kind="error" if error else "success",
        action_label=action_label,
        on_action=on_action,
        duration_ms=duration_ms,
    )


def show_info(
    page: ft.Page,
    *,
    title: str,
    message: str | None = None,
    content: ft.Control | None = None,
    ok_label: str = "Понятно",
) -> None:
    """Non-destructive info modal."""
    body: ft.Control
    if content is not None:
        body = content
    else:
        body = ft.Text(message or "", color=TEXT)
    page.show_dialog(
        ft.AlertDialog(
            title=ft.Text(title, color=TEXT),
            content=body,
            actions=[
                ft.TextButton(ok_label, on_click=lambda e: page.pop_dialog()),
            ],
        )
    )


def confirm_action(
    page: ft.Page,
    *,
    title: str,
    message: str,
    on_confirm,
    confirm_label: str = "ОК",
    cancel_label: str = "Отмена",
    danger: bool = False,
) -> None:
    """Confirm modal. ``danger=True`` styles the confirm button as destructive."""

    def _yes(_):
        page.pop_dialog()
        haptic(page, "heavy" if danger else "medium")
        on_confirm()

    confirm_color = RED if danger else ORANGE
    page.show_dialog(
        ft.AlertDialog(
            title=ft.Text(title, color=TEXT),
            content=ft.Text(message, color=TEXT),
            actions=[
                ft.TextButton(cancel_label, on_click=lambda e: page.pop_dialog()),
                ft.TextButton(
                    confirm_label,
                    on_click=_yes,
                    style=ft.ButtonStyle(color=confirm_color),
                ),
            ],
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
    confirm_action(
        page,
        title=title,
        message=message,
        on_confirm=on_confirm,
        confirm_label=confirm_label,
        danger=True,
    )


def set_field_error(field, message: str | None) -> None:
    """Field-level hint (Flet ``error_text``) plus border tint. No-op if unsupported."""
    if field is None:
        return
    text = (message or "").strip() or None
    try:
        field.error_text = text
    except Exception:
        pass
    try:
        if text:
            field.border_color = RED
            field.focused_border_color = RED
        else:
            field.border_color = BORDER
            field.focused_border_color = ORANGE
    except Exception:
        pass


def clear_field_error(field) -> None:
    set_field_error(field, None)


def validation_fail(page: ft.Page, message: str, field=None) -> None:
    """Never silent: field hint (if any) + error toast."""
    if field is not None:
        set_field_error(field, message)
    show_toast(page, message, kind="error")


def ru_validation_message(
    exc: BaseException,
    *,
    fallback: str = "Проверьте поля формы",
) -> str:
    """Map Pydantic / ValueError to a short Russian hint."""
    if isinstance(exc, ValidationError):
        errs = exc.errors()
        if not errs:
            return fallback
        loc = ".".join(str(x) for x in errs[0].get("loc", ()))
        for key, msg in _RU_BY_LOC.items():
            if key == loc or key in loc.split("."):
                return msg
        raw = str(errs[0].get("msg") or "")
        lowered = raw.lower()
        if "title required" in lowered or "string should have at least 1" in lowered:
            return "Введите название"
        if "greater than" in lowered or "greater_than" in str(errs[0].get("type") or ""):
            return "Значение должно быть больше 0"
        return fallback
    if isinstance(exc, ValueError):
        text = str(exc)
        lowered = text.lower()
        if "title" in lowered:
            return "Введите название"
        if ".md" in lowered or "файл" in lowered:
            return "Имя файла: только *.md без пути"
        return "Некорректное значение — проверьте поля"
    return fallback


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
