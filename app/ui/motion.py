"""Subtle motion tokens — 150–280ms, dark theme, not gaudy."""
from __future__ import annotations

import asyncio

import flet as ft

DURATION_FAST = 160
DURATION_MED = 220
DURATION_SLOW = 260
APPEAR_CAP = 12


def anim(ms: int = DURATION_MED, curve=None) -> ft.Animation:
    crv = curve if curve is not None else ft.AnimationCurve.EASE_OUT
    return ft.Animation(int(ms), crv)


def scale_of(value: float):
    """Flet 0.86 Scale(...) or a plain float, whichever the runtime accepts."""
    cls = getattr(ft, "Scale", None)
    if cls is None:
        return value
    try:
        return cls(scale=float(value))
    except TypeError:
        try:
            return cls(float(value))
        except Exception:
            return value
    except Exception:
        return value


def make_switcher(child: ft.Control | None = None) -> ft.Control:
    """Fade host for overlay / tab swaps. Falls back to a plain Container."""
    inner = child if child is not None else ft.Container(expand=True)
    transition = getattr(ft, "AnimatedSwitcherTransition", None)
    cls = getattr(ft, "AnimatedSwitcher", None)
    fade = getattr(transition, "FADE", None) if transition is not None else None
    extra = {}
    if fade is not None:
        extra["transition"] = fade
    extra["switch_in_curve"] = ft.AnimationCurve.EASE_OUT
    extra["switch_out_curve"] = ft.AnimationCurve.EASE_IN
    if cls is not None:
        attempts = [
            dict(content=inner, duration=DURATION_MED, reverse_duration=DURATION_FAST, **extra),
            dict(duration=DURATION_MED, reverse_duration=DURATION_FAST, **extra),
        ]
        for kwargs in attempts:
            try:
                if "content" in kwargs:
                    sw = cls(**kwargs)
                else:
                    sw = cls(inner, **kwargs)
                try:
                    sw.expand = True
                except Exception:
                    pass
                return sw
            except Exception:
                continue
    host = ft.Container(content=inner, expand=True, animate_opacity=anim(DURATION_MED))
    return host


def appear_item(control: ft.Control, *, index: int = 0) -> ft.Container:
    """List-row entrance: opacity + slight rise. First APPEAR_CAP rows only."""
    live = index < APPEAR_CAP
    wrap = ft.Container(
        content=control,
        opacity=0.0 if live else 1.0,
        offset=ft.Offset(0, 0.03) if live else ft.Offset(0, 0),
        animate_opacity=anim(DURATION_MED),
        animate_offset=anim(DURATION_SLOW),
    )
    wrap.data = {"appear": live}
    return wrap


def reveal_items(items: list[ft.Control], page: ft.Page | None = None) -> None:
    changed = False
    for item in items:
        flag = getattr(item, "data", None)
        if isinstance(flag, dict) and flag.get("appear"):
            item.opacity = 1.0
            item.offset = ft.Offset(0, 0)
            changed = True
    if changed and page is not None:
        try:
            page.update()
        except Exception:
            pass


def pulse_press(control) -> None:
    """Chip / button scale press (≈160ms)."""
    if control is None:
        return
    try:
        if getattr(control, "animate_scale", None) is None:
            control.animate_scale = anim(DURATION_FAST)
        control.scale = scale_of(0.96)
        try:
            control.update()
        except Exception:
            pass
        control.scale = scale_of(1.0)
        try:
            control.update()
        except Exception:
            pass
    except Exception:
        pass


def sheet_motion_wrap(child: ft.Control) -> ft.Container:
    """Overlay / sheet open: fade + tiny scale-in."""
    return ft.Container(
        content=child,
        opacity=0.0,
        scale=scale_of(0.98),
        animate_opacity=anim(DURATION_MED),
        animate_scale=anim(DURATION_SLOW),
    )


def open_sheet_motion(wrap: ft.Control, page: ft.Page | None = None) -> None:
    try:
        wrap.opacity = 1.0
        wrap.scale = scale_of(1.0)
        if page is not None:
            page.update()
    except Exception:
        pass


def splash_fade(root: ft.Control, page: ft.Page | None = None) -> ft.Control:
    """Splash: fade from 0 → 1 after first frame."""
    try:
        root.opacity = 0.0
        root.animate_opacity = anim(DURATION_SLOW)
    except Exception:
        return root

    async def _in():
        try:
            await asyncio.sleep(0.04)
            root.opacity = 1.0
            if page is not None:
                page.update()
        except Exception:
            try:
                root.opacity = 1.0
            except Exception:
                pass

    if page is not None:
        try:
            page.run_task(_in)
        except Exception:
            try:
                root.opacity = 1.0
            except Exception:
                pass
    else:
        try:
            root.opacity = 1.0
        except Exception:
            pass
    return root
