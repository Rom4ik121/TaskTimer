"""Full-screen PIN lock — charcoal, icon, dots, iOS pad, Face ID fallback."""
from __future__ import annotations

import flet as ft

from app.db import get_session
from app.services import lock_service
from app.ui.components.dialogs import show_snack
from app.ui.components.pin_pad import build_number_pad, build_pin_dots
from app.ui.theme import BG, MUTED, ORANGE, RED, TEXT, icon_src


def build_lock_screen(page: ft.Page, *, on_unlock, on_bind_keys=None) -> ft.Control:
    state = {"pin": "", "error": False, "shake": False, "hint": "Введите PIN"}

    title = ft.Text(
        "Введите PIN",
        size=22,
        weight=ft.FontWeight.W_700,
        color=TEXT,
        text_align=ft.TextAlign.CENTER,
    )
    hint = ft.Text(state["hint"], size=13, color=MUTED, text_align=ft.TextAlign.CENTER)
    dots_host = ft.Container()
    pad_host = ft.Container()

    def _lockout_hint(remaining: float) -> str:
        sec = max(1, int(round(remaining)))
        return f"Слишком много попыток · подождите {sec} с"

    def paint() -> None:
        with get_session() as session:
            remaining = lock_service.lockout_remaining_sec(session)
        locked = remaining > 0
        if locked:
            state["hint"] = _lockout_hint(remaining)
            hint.color = RED
        elif state["error"]:
            hint.color = RED
        else:
            state["hint"] = "Введите PIN"
            hint.color = MUTED
        hint.value = state["hint"]
        dots_host.content = build_pin_dots(
            len(state["pin"]),
            error=state["error"],
            shake=state["shake"],
        )
        pad_host.content = build_number_pad(
            on_digit=on_digit,
            on_backspace=on_backspace,
            disabled=locked,
        )
        try:
            page.update()
        except Exception:
            pass
        state["shake"] = False

    def submit(code: str) -> None:
        with get_session() as session:
            result = lock_service.unlock(session, code)
        if result.ok:
            state["pin"] = ""
            state["error"] = False
            on_unlock()
            return
        state["pin"] = ""
        state["error"] = True
        state["shake"] = bool(result.shake)
        if result.reason == "lockout":
            state["hint"] = _lockout_hint(result.lockout_remaining_sec)
        else:
            left = result.remaining_attempts
            state["hint"] = f"Неверный PIN · осталось {left}"
        paint()

    def on_digit(d: str) -> None:
        with get_session() as session:
            if lock_service.lockout_remaining_sec(session) > 0:
                paint()
                return
        if len(state["pin"]) >= lock_service.PIN_LENGTH:
            return
        state["error"] = False
        state["pin"] += d
        paint()
        if len(state["pin"]) == lock_service.PIN_LENGTH:
            submit(state["pin"])

    def on_backspace(_e=None) -> None:
        if state["pin"]:
            state["pin"] = state["pin"][:-1]
            state["error"] = False
            paint()

    def feed_key(key: str) -> None:
        if key in "0123456789":
            on_digit(key)
        elif key in ("back", "backspace", "delete"):
            on_backspace()

    if callable(on_bind_keys):
        on_bind_keys(feed_key)

    def on_face(_e=None) -> None:
        if lock_service.is_biometrics_available():
            on_unlock()
            return
        show_snack(page, lock_service.biometrics_unavailable_message(), error=True)

    icon = ft.Image(
        src=icon_src(small=True),
        width=88,
        height=88,
        fit=ft.BoxFit.CONTAIN,
    )
    face_btn = ft.Container(
        content=ft.Column(
            [
                ft.Icon(ft.Icons.FACE_UNLOCK_OUTLINED, color=ORANGE, size=26),
                ft.Text("Face ID", size=12, color=MUTED),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
        ),
        on_click=on_face,
        ink=True,
        padding=8,
    )
    paint()
    return ft.Container(
        content=ft.Column(
            [
                ft.Container(height=36),
                icon,
                ft.Container(height=8),
                ft.Text(
                    "TaskTimer",
                    size=16,
                    weight=ft.FontWeight.W_600,
                    color=ORANGE,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=18),
                title,
                ft.Container(height=6),
                hint,
                ft.Container(height=18),
                dots_host,
                ft.Container(height=28),
                pad_host,
                ft.Container(height=18),
                face_btn,
                ft.Text(
                    "или введите PIN",
                    size=11,
                    color=MUTED,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        ),
        bgcolor=BG,
        expand=True,
        padding=ft.Padding.only(left=16, right=16, top=12, bottom=16),
    )
