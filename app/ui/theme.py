"""Premium dark charcoal theme tokens with live accent."""
from __future__ import annotations

from pathlib import Path

import flet as ft

ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets"
ICON_PNG = ASSETS_DIR / "icon.png"
ICON_ICO = ASSETS_DIR / "icon.ico"


def icon_src() -> str:
    """Asset-relative name for ``ft.Image`` when ``ft.run(..., assets_dir=assets)``."""
    return "icon.png"


def window_icon_path() -> str | None:
    """Absolute path for ``page.window.icon`` (.ico preferred on Windows)."""
    if ICON_ICO.is_file():
        return str(ICON_ICO)
    if ICON_PNG.is_file():
        return str(ICON_PNG)
    return None

BG = "#0F0F12"
BG_ELEVATED = "#121212"
CARD = "#17171C"
CARD_ALT = "#1C1C22"
BORDER = "#2A2A32"
ORANGE = "#FF8A00"
ORANGE_DIM = "#CC6E00"
ORANGE_SOFT = "#FF8A0033"
WHITE = "#FFFFFF"
TEXT = "#F5F5F7"
MUTED = "#8A8A96"
MUTED2 = "#5C5C68"
GREEN = "#3DDC97"
RED = "#FF5C5C"
BLUE = "#4C8DFF"
PURPLE = "#A78BFA"
PHONE_W = 390
PHONE_H = 844
RADIUS = 14

# Named accent presets for Settings chips (label, hex)
ACCENT_PRESETS: list[tuple[str, str]] = [
    ("orange", "#FF8A00"),
    ("teal", "#14B8A6"),
    ("violet", "#8B5CF6"),
    ("rose", "#F43F5E"),
    ("blue", "#3B82F6"),
]

TAG_COLORS = {
    "оранжевый": ORANGE,
    "синий": BLUE,
    "зелёный": GREEN,
    "красный": RED,
    "фиолетовый": PURPLE,
    "нет": MUTED,
}

STATUS_LABELS = {
    "todo": "К выполнению",
    "in_progress": "В работе",
    "done": "Готово",
}
STATUS_COLORS = {
    "todo": MUTED,
    "in_progress": ORANGE,
    "done": GREEN,
}
PRIORITY_LABELS = {
    "low": "Низкий",
    "medium": "Средний",
    "high": "Высокий",
}
PRIORITY_COLORS = {
    "low": BLUE,
    "medium": ORANGE,
    "high": RED,
}
NODE_STATUS_LABELS = {
    "pending": "Ожидает",
    "active": "Активен",
    "done": "Готово",
}


def _normalize_hex(hex_color: str) -> str:
    v = (hex_color or "").strip()
    if not v:
        return "#FF8A00"
    if not v.startswith("#"):
        v = "#" + v
    if len(v) == 4:
        v = "#" + "".join(ch * 2 for ch in v[1:])
    return v.upper()


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = _normalize_hex(h)
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{max(0, min(255, r)):02X}{max(0, min(255, g)):02X}{max(0, min(255, b)):02X}"


def _dim_hex(h: str, factor: float = 0.8) -> str:
    r, g, b = _hex_to_rgb(h)
    return _rgb_to_hex(int(r * factor), int(g * factor), int(b * factor))


def apply_accent(hex_color: str, page: ft.Page | None = None) -> str:
    """Update live accent tokens (and optional page ColorScheme) without restart.

    Also patches ``ORANGE`` / ``ORANGE_DIM`` / ``ORANGE_SOFT`` already imported
    into other ``app.*`` modules (strings are rebound at import time).
    """
    global ORANGE, ORANGE_DIM, ORANGE_SOFT
    ORANGE = _normalize_hex(hex_color)
    ORANGE_DIM = _dim_hex(ORANGE, 0.8)
    ORANGE_SOFT = ORANGE + "33"
    TAG_COLORS["оранжевый"] = ORANGE
    STATUS_COLORS["in_progress"] = ORANGE
    PRIORITY_COLORS["medium"] = ORANGE
    # Sync star-imported / from-imported string bindings across app package
    import sys

    for name, mod in list(sys.modules.items()):
        if not name or not name.startswith("app.") or mod is None:
            continue
        d = getattr(mod, "__dict__", None)
        if not d:
            continue
        if "ORANGE" in d and isinstance(d.get("ORANGE"), str):
            d["ORANGE"] = ORANGE
        if "ORANGE_DIM" in d and isinstance(d.get("ORANGE_DIM"), str):
            d["ORANGE_DIM"] = ORANGE_DIM
        if "ORANGE_SOFT" in d and isinstance(d.get("ORANGE_SOFT"), str):
            d["ORANGE_SOFT"] = ORANGE_SOFT
    if page is not None:
        _set_page_theme(page)
        try:
            page.update()
        except Exception:
            pass
    return ORANGE


def _set_page_theme(page: ft.Page) -> None:
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = BG
    page.theme = ft.Theme(
        color_scheme_seed=ORANGE,
        scaffold_bgcolor=BG,
        card_bgcolor=CARD,
        divider_color=BORDER,
        color_scheme=ft.ColorScheme(
            primary=ORANGE,
            on_primary=BG,
            secondary=ORANGE_DIM,
            surface=CARD,
            on_surface=TEXT,
            on_surface_variant=MUTED,
            outline=BORDER,
            error=RED,
        ),
        navigation_bar_theme=ft.NavigationBarTheme(
            bgcolor=BG_ELEVATED,
            indicator_color=ORANGE_SOFT,
            label_text_style=ft.TextStyle(size=11, color=MUTED),
        ),
    )


def apply_theme(page: ft.Page, *, accent: str | None = None) -> None:
    if accent:
        apply_accent(accent)
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = BG
    page.padding = 0
    page.spacing = 0
    page.title = "TaskTimer"
    try:
        page.window.width = PHONE_W + 24
        page.window.height = PHONE_H + 48
        page.window.min_width = 360
        page.window.min_height = 700
    except Exception:
        pass
    try:
        ic = window_icon_path()
        if ic:
            page.window.icon = ic
    except Exception:
        pass
    _set_page_theme(page)


def card_style(*, accent: bool = False) -> dict:
    return {
        "bgcolor": CARD,
        "border_radius": ft.BorderRadius.all(RADIUS),
        "border": ft.Border.all(1, ORANGE if accent else BORDER),
    }



def section_title(text: str, trailing: ft.Control | None = None) -> ft.Control:
    row = [
        ft.Text(text, size=18, weight=ft.FontWeight.W_600, color=TEXT, expand=True),
    ]
    if trailing:
        row.append(trailing)
    return ft.Row(
        row,
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def muted(text: str, *, size: int = 12) -> ft.Text:
    return ft.Text(text, size=size, color=MUTED)



def markdown_lite(
    text: str,
    *,
    size: int = 13,
    color: str | None = None,
    muted_if_empty: str = "",
) -> ft.Control:
    """Render markdown-lite: ``**bold**`` → TextSpan with bold weight.

    Other markdown is left as plain text. Empty text returns muted placeholder
    (or an empty Text if ``muted_if_empty`` is blank).
    """
    import re

    fg = color or TEXT
    raw = (text or "").strip()
    if not raw:
        if muted_if_empty:
            return ft.Text(muted_if_empty, size=size, color=MUTED)
        return ft.Text("", size=size, color=fg)

    pattern = re.compile(r"\*\*(.+?)\*\*")
    spans: list[ft.TextSpan] = []
    pos = 0
    for m in pattern.finditer(raw):
        if m.start() > pos:
            spans.append(
                ft.TextSpan(raw[pos : m.start()], style=ft.TextStyle(color=fg, size=size))
            )
        spans.append(
            ft.TextSpan(
                m.group(1),
                style=ft.TextStyle(color=fg, size=size, weight=ft.FontWeight.W_700),
            )
        )
        pos = m.end()
    if pos < len(raw):
        spans.append(ft.TextSpan(raw[pos:], style=ft.TextStyle(color=fg, size=size)))
    if pattern.search(raw) and spans:
        return ft.Text(spans=spans, size=size, color=fg, selectable=True)
    return ft.Text(raw, size=size, color=fg, selectable=True)
