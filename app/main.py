"""TaskTimer entrypoint — premium dark iPhone-oriented task manager."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import flet as ft

from app.db import get_session, init_db
from app.services import lock_service, settings_service, task_service
from app.services.seed import seed_if_empty
from app.ui.components.nav import build_nav
from app.ui.screens.analytics import build_analytics
from app.ui.screens.create_task import build_create_task
from app.ui.screens.focus import build_focus
from app.ui.screens.goal_detail import build_goal_detail
from app.ui.screens.home import build_home
from app.ui.screens.lock_screen import build_lock_screen
from app.ui.screens.pin_setup import build_pin_setup
from app.ui.screens.reminders import build_reminders
from app.ui.screens.canvas_board import build_canvas_board
from app.ui.screens.note_editor import build_note_editor
from app.ui.screens.search import build_search
from app.ui.screens.settings import build_settings
from app.ui.screens.splash import build_splash
from app.ui.screens.task_detail import build_task_detail
from app.ui.screens.onboarding import maybe_show_onboarding
from app.ui.screens.tasks import build_tasks
from app.ui.haptics import attach as attach_haptics, haptic
from app.ui.motion import make_switcher
from app.ui.theme import ASSETS_DIR, BG, BG_ELEVATED, BORDER, PHONE_H, PHONE_W, apply_accent, apply_theme, is_mobile_layout


_INPUT_TYPE_NAMES = frozenset(
    {"TextField", "CupertinoTextField", "TextFormField"}
)


def _is_text_input_control(obj) -> bool:
    """True if obj looks like a Flet text input (type name or class)."""
    if obj is None:
        return False
    try:
        name = type(obj).__name__
    except Exception:
        name = ""
    if name in _INPUT_TYPE_NAMES:
        return True
    if isinstance(obj, str) and any(t.lower() in obj.lower() for t in _INPUT_TYPE_NAMES):
        return True
    return False


def _walk_controls(root):
    """Yield root and nested content / controls / overlay (best effort)."""
    if root is None:
        return
    seen: set[int] = set()
    stack = [root]
    while stack:
        cur = stack.pop()
        if cur is None:
            continue
        try:
            ident = id(cur)
        except Exception:
            ident = None
        if ident is not None:
            if ident in seen:
                continue
            seen.add(ident)
        yield cur
        content = getattr(cur, "content", None)
        if content is not None:
            stack.append(content)
        for attr in ("controls", "overlay"):
            kids = getattr(cur, attr, None)
            if kids:
                try:
                    stack.extend(list(kids))
                except Exception:
                    pass


def _control_flag_focused(ctrl) -> bool:
    for attr in ("focused", "_focused"):
        try:
            if bool(getattr(ctrl, attr, False)):
                return True
        except Exception:
            continue
    return False


def _any_text_input_focused(page) -> bool:
    """Walk the page tree for a TextField that reports focus."""
    try:
        for c in _walk_controls(page):
            if _is_text_input_control(c) and _control_flag_focused(c):
                return True
    except Exception:
        return False
    return False


def keyboard_from_text_input(e) -> bool:
    """Best-effort: ignore shortcuts while typing in a TextField.

    Flet KeyboardEvent.control is usually the Page; target is its id.
    If the API exposes a TextField as control/target, treat as typing.
    Else walk the page for a focused input. If focus cannot be determined,
    return False so Ctrl+N / Ctrl+F / Esc / Space / digits still fire.
    """
    try:
        ctrl = getattr(e, "control", None)
        tgt = getattr(e, "target", None)
        if _is_text_input_control(ctrl) or _is_text_input_control(tgt):
            return True
        page = None
        try:
            page = getattr(e, "page", None)
        except Exception:
            page = None
        if page is None:
            page = getattr(ctrl, "page", None)
        if page is None and type(ctrl).__name__ == "Page":
            page = ctrl
        if page is not None and _any_text_input_focused(page):
            return True
    except Exception:
        return False
    return False



# Overlay screens closed by Esc (not main tabs). Lock / PIN / splash never bypass.
_OVERLAY_SCREENS = frozenset(
    {"search", "create", "settings", "focus", "task", "goal", "note", "reminders"}
)
_GATE_SCREENS = frozenset({"lock", "pin_setup", "splash", "onboarding"})



def digit_switches_tab(key: str, screen: str) -> int | None:
    """Map digit key 1–4 → bottom nav index 0–3 when on main screen.

    Keys are 1-based (1=Дом … 3=Холст … 4=Статы); indices are 0-based.
    Returns None if not on main or key is not 1–4.
    Accepts plain "1".."4" and Flet-style "digit1".."digit4".
    """
    if (screen or "") != "main":
        return None
    k = (key or "").strip().lower()
    # Strip optional "digit" / "numpad" prefixes from some backends.
    for prefix in ("digit", "numpad"):
        if k.startswith(prefix) and len(k) > len(prefix):
            k = k[len(prefix) :]
    mapping = {"1": 0, "2": 1, "3": 2, "4": 3}
    return mapping.get(k)



def space_opens_focus(key: str, screen: str) -> bool:
    """True if Space should open Focus when on main (not overlays).

    Accepts " " / "space" (any case). Caller must gate TextField + Ctrl/Alt.
    """
    if (screen or "") != "main":
        return False
    raw = key if key is not None else ""
    if raw == " " or (len(raw) == 1 and raw.isspace()):
        return True
    return raw.strip().lower() == "space"


def escape_closes_overlay(screen: str, leave_cb) -> bool:
    """If *screen* is an overlay, call *leave_cb* (from main) and return True."""
    if screen in _OVERLAY_SCREENS:
        leave_cb()
        return True
    return False


def main(page: ft.Page) -> None:
    init_db()
    seed_if_empty()
    with get_session() as session:
        accent = settings_service.get_settings(session).accent_hex
    apply_accent(accent)
    apply_theme(page, accent=accent)
    attach_haptics(page)
    try:
        lock_service.set_runtime_platform(getattr(page, "platform", None))
    except Exception:
        pass
    if not is_mobile_layout(page):
        try:
            page.window.icon = str(ASSETS_DIR / "icon.ico" if (ASSETS_DIR / "icon.ico").is_file() else ASSETS_DIR / "icon.png")
        except Exception:
            pass

    state = {
        "tab": 0,
        "screen": "splash",  # splash | onboarding | pin_setup | lock | main | overlays
        "task_id": None,
        "goal_id": None,
        "note_filename": None,
        "note_title": None,
        "tasks_filter": None,
        "pin_setup_mode": "setup",
        "pin_setup_from": "launch",
        "pin_key_handler": None,
        "unlocked": False,
    }
    with get_session() as session:
        if lock_service.should_gate_main(session):
            state["screen"] = "lock"
    content = make_switcher(ft.Container(expand=True))
    nav_host = ft.Container()

    def go_create():
        state["screen"] = "create"
        render()

    def go_task(tid: int):
        state["screen"] = "task"
        state["task_id"] = tid
        render()

    def go_goal(gid: int):
        state["screen"] = "goal"
        state["goal_id"] = gid
        render()

    def go_focus():
        state["screen"] = "focus"
        render()

    def go_settings():
        state["screen"] = "settings"
        render()

    def go_reminders():
        state["screen"] = "reminders"
        render()

    def go_search():
        state["screen"] = "search"
        render()

    def go_note(filename: str, title: str | None = None):
        state["screen"] = "note"
        state["note_filename"] = filename
        state["note_title"] = title
        render()

    def go_tasks_overdue():
        state["tab"] = 1
        state["screen"] = "main"
        state["tasks_filter"] = "overdue"
        state["task_id"] = None
        state["goal_id"] = None
        render()

    def go_tasks_due_today():
        state["tab"] = 1
        state["screen"] = "main"
        state["tasks_filter"] = "due_today"
        state["task_id"] = None
        state["goal_id"] = None
        render()

    def leave_overlay():
        state["screen"] = "main"
        state["task_id"] = None
        state["goal_id"] = None
        state["note_filename"] = None
        state["note_title"] = None
        render()

    def bind_pin_keys(fn) -> None:
        state["pin_key_handler"] = fn

    def enter_app() -> None:
        state["unlocked"] = True
        state["pin_key_handler"] = None
        state["screen"] = "main"
        render()

    def go_lock() -> None:
        state["screen"] = "lock"
        state["unlocked"] = False
        render()

    def go_pin_setup(*, mode: str = "setup", from_settings: bool = False) -> None:
        state["pin_setup_mode"] = mode
        state["pin_setup_from"] = "settings" if from_settings else "launch"
        state["screen"] = "pin_setup"
        render()

    def after_pin_setup() -> None:
        if state.get("pin_setup_from") == "settings":
            state["pin_key_handler"] = None
            state["screen"] = "settings"
            render()
            return
        enter_app()

    def cancel_pin_setup() -> None:
        if state.get("pin_setup_from") == "settings":
            state["pin_key_handler"] = None
            state["screen"] = "settings"
            render()
            return
        skip_pin_setup()

    def skip_pin_setup() -> None:
        with get_session() as session:
            lock_service.skip_lock_setup(session)
        after_pin_setup()

    def continue_after_onboarding() -> None:
        with get_session() as session:
            needs_setup = lock_service.needs_pin_setup(session)
            gate = lock_service.should_gate_main(session)
        if needs_setup:
            go_pin_setup(mode="setup", from_settings=False)
            return
        if gate:
            go_lock()
            return
        enter_app()

    def after_splash() -> None:
        with get_session() as session:
            gate = lock_service.should_gate_main(session)
            needs_setup = lock_service.needs_pin_setup(session)
            onboarded = settings_service.is_onboarded(session)
        if gate:
            go_lock()
            return
        if not onboarded:
            state["screen"] = "onboarding"
            render()
            maybe_show_onboarding(page, on_done=continue_after_onboarding)
            return
        if needs_setup:
            go_pin_setup(mode="setup", from_settings=False)
            return
        enter_app()

    def refresh_all():
        render()

    def on_nav(e: ft.ControlEvent):
        state["tab"] = int(e.control.selected_index)
        state["screen"] = "main"
        state["task_id"] = None
        state["goal_id"] = None
        state["note_filename"] = None
        state["note_title"] = None
        state["tasks_filter"] = None
        haptic(page, "selection")
        render()

    def render():
        screen = state["screen"]
        if screen == "splash":
            content.content = build_splash(page, on_done=after_splash)
            nav_host.visible = False
        elif screen == "onboarding":
            content.content = build_splash(
                page, on_done=lambda: None, auto_ms=0, skippable=False
            )
            nav_host.visible = False
        elif screen == "lock":
            content.content = build_lock_screen(
                page, on_unlock=enter_app, on_bind_keys=bind_pin_keys
            )
            nav_host.visible = False
        elif screen == "pin_setup":
            from_settings = state.get("pin_setup_from") == "settings"
            mode = state.get("pin_setup_mode") or "setup"
            content.content = build_pin_setup(
                page,
                on_done=after_pin_setup,
                on_skip=cancel_pin_setup,
                allow_skip=not from_settings,
                mode=mode,
                on_bind_keys=bind_pin_keys,
            )
            nav_host.visible = False
        elif screen == "create":
            content.content = build_create_task(
                page, on_done=leave_overlay, refresh_all=refresh_all
            )
            nav_host.visible = False
        elif screen == "task" and state["task_id"]:
            content.content = build_task_detail(
                page,
                state["task_id"],
                on_back=leave_overlay,
                refresh_all=refresh_all,
                on_open_task=go_task,
            )
            nav_host.visible = False
        elif screen == "goal" and state["goal_id"]:
            content.content = build_goal_detail(
                page,
                state["goal_id"],
                on_back=leave_overlay,
                refresh_all=refresh_all,
            )
            nav_host.visible = False
        elif screen == "focus":
            content.content = build_focus(
                page,
                on_back=leave_overlay,
                refresh_all=refresh_all,
                on_open_note=go_note,
            )
            nav_host.visible = False
        elif screen == "settings":
            content.content = build_settings(
                page,
                on_back=leave_overlay,
                refresh_all=refresh_all,
                on_setup_pin=lambda: go_pin_setup(mode="setup", from_settings=True),
                on_change_pin=lambda: go_pin_setup(mode="change", from_settings=True),
            )
            nav_host.visible = False
        elif screen == "reminders":
            content.content = build_reminders(
                page,
                on_back=leave_overlay,
                on_open_task=go_task,
                on_open_goal=go_goal,
                on_open_overdue=go_tasks_overdue,
            )
            nav_host.visible = False
        elif screen == "search":
            content.content = build_search(
                page,
                on_back=leave_overlay,
                on_open_task=go_task,
                on_open_goal=go_goal,
            )
            nav_host.visible = False
        elif screen == "note" and state.get("note_filename"):
            content.content = build_note_editor(
                page,
                filename=state["note_filename"],
                on_back=leave_overlay,
                refresh_all=refresh_all,
                title_override=state.get("note_title"),
            )
            nav_host.visible = False
        else:
            tab = state["tab"]
            if tab == 0:
                content.content = build_home(
                    page,
                    on_add=go_create,
                    refresh_all=refresh_all,
                    on_open_task=go_task,
                    on_open_goal=go_goal,
                    on_open_focus=go_focus,
                    on_open_settings=go_settings,
                    on_open_overdue=go_tasks_overdue,
                    on_open_reminders=go_reminders,
                    on_open_due_today=go_tasks_due_today,
                    on_open_search=go_search,
                    on_open_note=go_note,
                )
            elif tab == 1:
                initial = state.get("tasks_filter")
                state["tasks_filter"] = None
                content.content = build_tasks(
                    page,
                    on_add=go_create,
                    refresh_all=refresh_all,
                    on_open_task=go_task,
                    initial_filter=initial,
                    on_open_search=go_search,
                    on_open_note=go_note,
                )
            elif tab == 2:
                content.content = build_canvas_board(
                    page,
                    refresh_all=refresh_all,
                    on_open_note=go_note,
                )
            else:
                content.content = build_analytics(
                    page,
                    refresh_all=refresh_all,
                    on_open_focus=go_focus,
                    on_open_note=go_note,
                )
            active_count = 0
            try:
                with get_session() as _s:
                    active_count = sum(
                        1
                        for t in task_service.list_tasks(_s, archived=False)
                        if getattr(t, "status", None) != "done"
                    )
            except Exception:
                active_count = 0
            nav_host.content = build_nav(tab, on_nav, tasks_badge=active_count)
            nav_host.visible = True
        page.update()

    shell_body = ft.Column(
        [
            content,
            ft.Container(height=1, bgcolor=BORDER),
            nav_host,
        ],
        spacing=0,
        expand=True,
    )

    mobile = is_mobile_layout(page)
    if mobile:
        # Real iPhone / Android: full screen, no decorative phone chrome.
        phone = ft.Container(
            content=shell_body,
            expand=True,
            bgcolor=BG,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )
        try:
            root = ft.SafeArea(content=phone, expand=True)
        except Exception:
            root = ft.Container(
                content=phone,
                expand=True,
                bgcolor=BG,
                padding=ft.Padding.only(top=12, bottom=8),
            )
        page_shell = ft.Container(
            content=root,
            alignment=ft.Alignment.CENTER,
            expand=True,
            bgcolor=BG,
            padding=0,
        )
    else:
        # Desktop preview: fixed 390×844 phone frame.
        phone = ft.Container(
            content=shell_body,
            width=PHONE_W,
            height=PHONE_H,
            bgcolor=BG,
            border=ft.Border.all(1, BORDER),
            border_radius=ft.BorderRadius.all(28),
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )
        page_shell = ft.Container(
            content=phone,
            alignment=ft.Alignment.CENTER,
            expand=True,
            bgcolor=BG_ELEVATED,
            padding=12,
        )


    def on_keyboard(e: ft.KeyboardEvent):
        # Desktop / native: Ctrl+N → create, Ctrl+F → search, Esc → leave overlay,
        # 1/2/3/4 → bottom tabs on main, Space → Focus on main (not in TextField).
        # On web, browsers often intercept Ctrl+N (new window) and Ctrl+F
        # (find in page) so the shortcut may never reach the app.
        if keyboard_from_text_input(e):
            return
        try:
            raw_key = e.key if e.key is not None else ""
        except Exception:
            raw_key = ""
        # Normalize Space before strip (lone " " would become "").
        if raw_key == " " or (len(raw_key) == 1 and raw_key.isspace()):
            key = "space"
        else:
            key = raw_key.strip().lower()
        ctrl = bool(getattr(e, "ctrl", False))
        alt = bool(getattr(e, "alt", False))
        screen_now = state.get("screen") or "main"
        # Esc / shortcuts never bypass lock, PIN setup, or splash.
        if screen_now in _GATE_SCREENS:
            handler = state.get("pin_key_handler")
            if key in ("escape", "esc"):
                return
            if callable(handler) and not ctrl and not alt:
                if key in "0123456789" or key.isdigit():
                    handler(key[-1] if key else key)
                elif key in ("backspace", "delete", "back"):
                    handler("back")
            return
        # Esc closes search/create/settings/focus/detail when not in a TextField.
        if key in ("escape", "esc") and not alt:
            escape_closes_overlay(state.get("screen") or "main", leave_overlay)
            return
        # Digit 1–4 switch bottom tabs; Space opens Focus — on main, no modifiers.
        if not ctrl and not alt:
            screen_now = state.get("screen") or "main"
            tab_idx = digit_switches_tab(key, screen_now)
            if tab_idx is not None:
                state["tab"] = tab_idx
                state["screen"] = "main"
                state["task_id"] = None
                state["goal_id"] = None
                state["note_filename"] = None
                state["note_title"] = None
                state["tasks_filter"] = None
                haptic(page, "selection")
                render()
                return
            if space_opens_focus(key, screen_now):
                if state.get("screen") != "focus":
                    go_focus()
                return
        if not ctrl or alt:
            return
        if key == "n":
            if state.get("screen") != "create":
                go_create()
        elif key == "f":
            if state.get("screen") != "search":
                go_search()

    page.on_keyboard_event = on_keyboard

    page.add(page_shell)
    render()
    # Launch flow starts on splash; onboarding / PIN / lock follow from after_splash.


if __name__ == "__main__":
    ft.run(main, assets_dir=str(ASSETS_DIR))
