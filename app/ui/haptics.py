"""Device haptics (iOS/Android) with a quiet desktop fallback."""
from __future__ import annotations

from typing import Literal

import flet as ft

from app.ui.theme import platform_name

from app.ui.motion import pulse_press as _pulse_press

HapticKind = Literal["light", "medium", "heavy", "selection", "success"]

_enabled: bool | None = None
_service = None


def is_enabled() -> bool:
    """Cached tactility flag (default on)."""
    global _enabled
    if _enabled is not None:
        return bool(_enabled)
    try:
        from app.db import get_session
        from app.services import settings_service

        with get_session() as session:
            _enabled = bool(getattr(settings_service.get_settings(session), "haptics_enabled", True))
    except Exception:
        _enabled = True
    return bool(_enabled)


def set_enabled(value: bool) -> None:
    global _enabled
    _enabled = bool(value)


def attach(page: ft.Page | None) -> None:
    """Bind Flet HapticFeedback once if the runtime exposes it."""
    global _service
    if page is None or _service is not None:
        return
    cls = getattr(ft, "HapticFeedback", None)
    if cls is None:
        return
    try:
        hf = cls()
    except Exception:
        return
    _service = hf
    try:
        services = getattr(page, "services", None)
        if services is None:
            page.services = [hf]
        elif hf not in list(services):
            services.append(hf)
    except Exception:
        pass


def haptic(page: ft.Page | None = None, kind: HapticKind = "light", *, control=None) -> None:
    """Fire haptic feedback. Never raises. Desktop: optional scale pulse."""
    if not is_enabled():
        return
    if page is not None:
        attach(page)
    plat = platform_name(page)
    mobile = plat in ("ios", "android", "android_tv")
    if mobile:
        if _fire_mobile(page, kind):
            return
    if control is not None:
        _pulse_control(control)
        return
    if not mobile:
        return
    _invoke_platform(page, kind)


def _fire_mobile(page: ft.Page | None, kind: HapticKind) -> bool:
    hf = _service
    if hf is None:
        return False
    method_name = {
        "light": "light_impact",
        "medium": "medium_impact",
        "heavy": "heavy_impact",
        "selection": "selection_click",
        "success": "medium_impact",
    }.get(kind, "light_impact")
    fn = getattr(hf, method_name, None)
    if not callable(fn):
        fn = getattr(hf, "vibrate", None)
    if not callable(fn):
        return False
    try:
        if page is not None and hasattr(page, "run_task"):
            async def _run():
                try:
                    await fn()
                except TypeError:
                    fn()
                except Exception:
                    pass

            page.run_task(_run)
            return True
        fn()
        return True
    except Exception:
        return False


def _invoke_platform(page: ft.Page | None, kind: HapticKind) -> None:
    if page is None or not hasattr(page, "invoke_method"):
        return
    flutter = {
        "light": "HapticFeedback.lightImpact",
        "medium": "HapticFeedback.mediumImpact",
        "heavy": "HapticFeedback.heavyImpact",
        "selection": "HapticFeedback.selectionClick",
        "success": "HapticFeedback.mediumImpact",
    }.get(kind, "HapticFeedback.lightImpact")
    try:
        page.invoke_method(flutter)
    except Exception:
        try:
            page.invoke_method("haptic", {"type": kind})
        except Exception:
            pass


def _pulse_control(control) -> None:
    """Short visual press pulse on desktop (no vibration)."""
    if control is None:
        return
    if _pulse_press is not None:
        try:
            _pulse_press(control)
            return
        except Exception:
            pass
    try:
        old = getattr(control, "opacity", 1.0)
        control.opacity = 0.82
        control.update()
        control.opacity = old if old is not None else 1.0
        control.update()
    except Exception:
        pass
