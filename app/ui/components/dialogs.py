"""Shared toasts, info/confirm modals, and form validation helpers."""
from __future__ import annotations

from typing import Literal

import flet as ft
from pydantic import ValidationError

from app.ui.theme import BG, BORDER, CARD, GREEN, MUTED, ORANGE, RED, TEXT, group_heading


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
    page.show_dialog(
        ft.SnackBar(
            ft.Text(message, color=fg),
            **kwargs,
        )
    )


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


def choice_chip(
    label: str,
    *,
    active: bool,
    accent: str = ORANGE,
    on_click=None,
    data=None,
) -> ft.Container:
    """Filter/choice chip used inside ``show_filter_sheet`` (dark theme)."""
    chip = ft.Container(
        content=ft.Text(
            label,
            size=12,
            color="#0F0F12" if active else MUTED,
            weight=ft.FontWeight.W_500,
        ),
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        border_radius=ft.BorderRadius.all(16),
        bgcolor=accent if active else "transparent",
        border=ft.Border.all(1, accent if active else BORDER),
        on_click=on_click,
        ink=True,
    )
    chip.data = data
    return chip


def _sheet_height(page: ft.Page) -> int:
    try:
        h = float(getattr(page, "height", None) or 0)
    except (TypeError, ValueError):
        h = 0.0
    if h <= 0:
        return 520
    return int(min(640, max(380, h * 0.78)))


def show_filter_sheet(
    page: ft.Page,
    *,
    title: str = "Фильтры",
    subtitle: str | None = None,
    sections: list[dict],
    on_apply,
    reset_values: dict | None = None,
    apply_label: str = "Готово",
    reset_label: str = "Сбросить",
) -> None:
    """Bottom sheet with chip sections + Сбросить / Готово.

    Each section: ``{"key", "title", "options": [(label, value), ...],
    "value", optional "accents": {value: color}}``.
    ``on_apply(values)`` runs after Готово; swipe-dismiss discards the draft.
    """
    draft = {sec["key"]: sec.get("value") for sec in sections}
    chip_map: dict[str, list[ft.Container]] = {sec["key"]: [] for sec in sections}
    closed = {"done": False}

    def _accent_for(sec: dict, value) -> str:
        accents = sec.get("accents") or {}
        if value in accents:
            return accents[value]
        return ORANGE

    def _paint_section(sec: dict) -> None:
        key = sec["key"]
        current = draft.get(key)
        for chip in chip_map[key]:
            val = chip.data
            active = current == val
            accent = _accent_for(sec, val)
            chip.bgcolor = accent if active else "transparent"
            chip.border = ft.Border.all(1, accent if active else BORDER)
            content = getattr(chip, "content", None)
            if content is not None and hasattr(content, "color"):
                content.color = "#0F0F12" if active else MUTED

    def _paint_all() -> None:
        for sec in sections:
            _paint_section(sec)

    def _finish(*, apply: bool) -> None:
        if closed["done"]:
            return
        closed["done"] = True
        try:
            page.pop_dialog()
        except Exception:
            pass
        if apply and callable(on_apply):
            on_apply(dict(draft))

    def on_reset(_e=None) -> None:
        defaults = reset_values if reset_values is not None else {sec["key"]: None for sec in sections}
        for key in list(draft.keys()):
            draft[key] = defaults.get(key)
        _paint_all()
        page.update()

    def on_done(_e=None) -> None:
        _finish(apply=True)

    section_controls: list[ft.Control] = []
    for sec in sections:
        chips: list[ft.Container] = []
        for label, val in sec.get("options") or []:
            chip = choice_chip(
                label,
                active=draft.get(sec["key"]) == val,
                accent=_accent_for(sec, val),
                data=val,
            )

            def _on_chip(_e=None, section=sec, value=val):
                draft[section["key"]] = value
                _paint_section(section)
                page.update()

            chip.on_click = _on_chip
            chips.append(chip)
            chip_map[sec["key"]].append(chip)
        section_controls.append(group_heading(sec.get("title") or sec["key"]))
        section_controls.append(
            ft.Row(
                chips,
                spacing=8,
                run_spacing=8,
                wrap=True,
            )
        )

    done_btn = ft.Container(
        content=ft.Text(
            apply_label,
            size=15,
            weight=ft.FontWeight.W_700,
            color=BG,
        ),
        bgcolor=ORANGE,
        padding=ft.Padding.symmetric(horizontal=18, vertical=12),
        border_radius=ft.BorderRadius.all(14),
        alignment=ft.Alignment.CENTER,
        expand=True,
        ink=True,
        on_click=on_done,
    )
    reset_btn = ft.TextButton(
        reset_label,
        on_click=on_reset,
        style=ft.ButtonStyle(color=MUTED),
    )

    header_controls: list[ft.Control] = [
        ft.Text(title, size=20, weight=ft.FontWeight.W_700, color=TEXT),
    ]
    if subtitle:
        header_controls.append(ft.Text(subtitle, size=12, color=MUTED))

    body = ft.Container(
        content=ft.Column(
            [
                *header_controls,
                ft.Column(
                    section_controls,
                    spacing=10,
                    scroll=ft.ScrollMode.AUTO,
                    expand=True,
                ),
                ft.Row(
                    [reset_btn, done_btn],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=12,
            expand=True,
        ),
        padding=ft.Padding.only(left=16, right=16, top=8, bottom=20),
        bgcolor=CARD,
        height=_sheet_height(page),
    )

    sheet = ft.BottomSheet(
        content=body,
        bgcolor=CARD,
        dismissible=True,
        draggable=True,
        show_drag_handle=True,
        on_dismiss=lambda e: _finish(apply=False),
    )
    page.show_dialog(sheet)
