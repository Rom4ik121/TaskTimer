"""First-run / settings PIN setup: enter → confirm → optional Face ID."""
from __future__ import annotations

import flet as ft

from app.db import get_session
from app.services import lock_service
from app.ui.components.dialogs import show_toast
from app.ui.components.pin_pad import build_number_pad, build_pin_dots
from app.ui.theme import BG, BORDER, CARD, MUTED, ORANGE, RED, TEXT


def build_pin_setup(
    page: ft.Page,
    *,
    on_done,
    on_skip=None,
    allow_skip: bool = True,
    mode: str = "setup",
    on_bind_keys=None,
) -> ft.Control:
    """mode: setup (first launch) | change (from Settings)."""
    is_change = mode == "change"
    state = {
        "step": "enter",  # enter | confirm | bio
        "first": "",
        "pin": "",
        "error": False,
        "shake": False,
        "bio": False,
    }

    heading = ft.Text(
        "Сменить PIN" if is_change else "Защитите приложение",
        size=22,
        weight=ft.FontWeight.W_700,
        color=TEXT,
        text_align=ft.TextAlign.CENTER,
    )
    subtitle = ft.Text("", size=13, color=MUTED, text_align=ft.TextAlign.CENTER)
    error_txt = ft.Text("", size=12, color=RED, text_align=ft.TextAlign.CENTER)
    dots_host = ft.Container()
    pad_host = ft.Container()
    bio_host = ft.Container()
    skip_host = ft.Container()

    def _subtitle() -> str:
        step = state["step"]
        if step == "enter":
            return "Придумайте 4-значный PIN"
        if step == "confirm":
            return "Повторите PIN"
        return "Разблокировка Face ID / биометрия"

    def paint() -> None:
        subtitle.value = _subtitle()
        error_txt.value = (
            "PIN не совпадает — попробуйте снова" if state["error"] else ""
        )
        show_pad = state["step"] in ("enter", "confirm")
        dots_host.visible = show_pad
        pad_host.visible = show_pad
        dots_host.content = build_pin_dots(
            len(state["pin"]),
            error=state["error"],
            shake=state["shake"],
        )
        pad_host.content = build_number_pad(
            on_digit=on_digit,
            on_backspace=on_backspace,
        )
        if state["step"] == "bio":
            bio_sw = ft.Switch(
                label="Разблокировка Face ID / биометрия",
                value=bool(state["bio"]),
                active_color=ORANGE,
                on_change=lambda e: _set_bio(bool(e.control.value)),
            )
            bio_note = ft.Text(
                lock_service.biometrics_unavailable_message()
                if not lock_service.is_biometrics_available()
                else "Можно включить Face ID на этом устройстве.",
                size=12,
                color=MUTED,
            )
            cont = ft.Container(
                content=ft.Text(
                    "Продолжить",
                    size=15,
                    weight=ft.FontWeight.W_700,
                    color="#0F0F12",
                ),
                bgcolor=ORANGE,
                padding=16,
                border_radius=ft.BorderRadius.all(14),
                alignment=ft.Alignment.CENTER,
                on_click=lambda e: _finish(bool(state["bio"])),
                ink=True,
            )
            bio_host.content = ft.Container(
                content=ft.Column(
                    [bio_sw, bio_note, ft.Container(height=8), cont],
                    spacing=10,
                ),
                padding=16,
                bgcolor=CARD,
                border=ft.Border.all(1, BORDER),
                border_radius=ft.BorderRadius.all(14),
            )
            bio_host.visible = True
        else:
            bio_host.visible = False
            bio_host.content = None
        if callable(on_skip):
            skip_label = "Настроить позже" if allow_skip and not is_change else "Отмена"
            skip_host.content = ft.TextButton(
                skip_label,
                on_click=lambda e: on_skip(),
                style=ft.ButtonStyle(color=MUTED),
            )
            skip_host.visible = True
        else:
            skip_host.visible = False
            skip_host.content = None
        try:
            page.update()
        except Exception:
            pass
        state["shake"] = False

    def _set_bio(v: bool) -> None:
        state["bio"] = v
        if v and not lock_service.is_biometrics_available():
            show_toast(page, lock_service.biometrics_unavailable_message(), kind="warning")

    def _finish(bio: bool) -> None:
        pin = state["first"]
        with get_session() as session:
            if is_change:
                lock_service.change_pin(session, pin)
            else:
                lock_service.setup_pin(session, pin, biometrics=bio)
        on_done()

    def _accept_code(code: str) -> None:
        if state["step"] == "enter":
            state["first"] = code
            state["pin"] = ""
            state["step"] = "confirm"
            state["error"] = False
            paint()
            return
        if code != state["first"]:
            state["pin"] = ""
            state["error"] = True
            state["shake"] = True
            state["step"] = "enter"
            state["first"] = ""
            paint()
            show_toast(page, "PIN не совпадает — введите заново", kind="error")
            return
        if is_change:
            _finish(False)
            return
        state["pin"] = ""
        state["step"] = "bio"
        state["error"] = False
        paint()

    def on_digit(d: str) -> None:
        if state["step"] not in ("enter", "confirm"):
            return
        if len(state["pin"]) >= lock_service.PIN_LENGTH:
            return
        state["error"] = False
        state["pin"] += d
        paint()
        if len(state["pin"]) == lock_service.PIN_LENGTH:
            _accept_code(state["pin"])

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

    paint()
    return ft.Container(
        content=ft.Column(
            [
                ft.Container(height=28),
                ft.Icon(ft.Icons.LOCK_OUTLINED, color=ORANGE, size=36),
                ft.Container(height=10),
                heading,
                ft.Container(height=6),
                subtitle,
                ft.Container(height=4),
                error_txt,
                ft.Container(height=16),
                dots_host,
                ft.Container(height=22),
                pad_host,
                ft.Container(height=12),
                bio_host,
                ft.Container(expand=True),
                skip_host,
                ft.Container(height=8),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        ),
        bgcolor=BG,
        expand=True,
        padding=ft.Padding.only(left=16, right=16, top=12, bottom=12),
    )
