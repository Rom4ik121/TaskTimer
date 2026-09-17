"""Reusable bento cards."""
from __future__ import annotations

from datetime import date

import flet as ft

from app.models import Goal, Task
from app.ui.components.progress_ring import mini_ring
from app.ui.theme import (
    MUTED,
    ORANGE,
    GREEN,
    RED,
    PRIORITY_COLORS,
    PRIORITY_LABELS,
    STATUS_COLORS,
    STATUS_LABELS,
    TAG_COLORS,
    TEXT,
    card_style,
)

_ANIM = ft.Animation(200, ft.AnimationCurve.EASE_OUT)


def _is_overdue(task: Task) -> bool:
    return (
        task.status != "done"
        and task.due_date is not None
        and task.due_date < date.today()
    )


def _is_due_today(task: Task) -> bool:
    return (
        task.status != "done"
        and task.due_date is not None
        and task.due_date == date.today()
    )


def _subtask_progress(task: Task) -> tuple[int, int] | None:
    """Return (done, total) if subtasks are safely loaded; else None."""
    try:
        if "subtasks" not in getattr(task, "__dict__", {}):
            subs = getattr(task, "subtasks", None)
        else:
            subs = task.__dict__.get("subtasks")
        if subs is None:
            return None
        total = len(subs)
        if total <= 0:
            return None
        done = sum(1 for s in subs if getattr(s, "done", False))
        return done, total
    except Exception:
        return None


def empty_state(
    title: str,
    hint: str = "",
    *,
    icon=None,
    emoji: str | None = None,
    action_label: str | None = None,
    on_action=None,
) -> ft.Control:
    if emoji:
        illustration: ft.Control = ft.Text(emoji, size=40, text_align=ft.TextAlign.CENTER)
    else:
        illustration = ft.Icon(icon or ft.Icons.INBOX_OUTLINED, size=36, color=MUTED)
    controls: list[ft.Control] = [
        illustration,
        ft.Text(title, size=14, weight=ft.FontWeight.W_600, color=TEXT),
    ]
    if hint:
        controls.append(
            ft.Text(hint, size=12, color=MUTED, text_align=ft.TextAlign.CENTER)
        )
    if action_label and on_action:
        controls.append(
            ft.Container(
                content=ft.Text(
                    action_label,
                    size=12,
                    weight=ft.FontWeight.W_700,
                    color="#0F0F12",
                ),
                bgcolor=ORANGE,
                padding=ft.Padding.symmetric(horizontal=16, vertical=10),
                border_radius=ft.BorderRadius.all(20),
                on_click=lambda e: on_action(),
                ink=True,
                animate=_ANIM,
            )
        )
    return ft.Container(
        content=ft.Column(
            controls,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
        ),
        padding=28,
        alignment=ft.Alignment.CENTER,
        animate=_ANIM,
        **card_style(),
    )



def empty_illus(title: str, *, emoji: str = "📭", hint: str = "") -> ft.Control:
    """Compact emoji + muted text for inline empties (not a full card)."""
    col = [
        ft.Text(emoji, size=28, text_align=ft.TextAlign.CENTER),
        ft.Text(title, size=12, color=MUTED, text_align=ft.TextAlign.CENTER),
    ]
    if hint:
        col.append(ft.Text(hint, size=11, color=MUTED, text_align=ft.TextAlign.CENTER))
    return ft.Container(
        content=ft.Column(
            col,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
        ),
        padding=ft.Padding.symmetric(horizontal=8, vertical=12),
        alignment=ft.Alignment.CENTER,
    )


def task_card(
    task: Task,
    *,
    on_tap=None,
    on_cycle_status=None,
    on_delete=None,
    on_toggle_pin=None,
    select_mode: bool = False,
    selected: bool = False,
    on_toggle_select=None,
    compact: bool = False,
) -> ft.Control:
    status_color = STATUS_COLORS.get(task.status, MUTED)
    pri_color = PRIORITY_COLORS.get(task.priority, ORANGE)
    from app.services.task_service import format_due_label

    overdue = _is_overdue(task)
    due_today = (not overdue) and _is_due_today(task)
    due, due_kind = format_due_label(task)
    if due_kind == "overdue":
        due = f"⚠ {due}"
        due_color = RED
    elif due_kind in ("today", "soon"):
        due_color = ORANGE
    else:
        due_color = MUTED
    tag = getattr(task, "color_tag", None)
    tag_color = TAG_COLORS.get(tag or "", MUTED) if tag else None
    progress = _subtask_progress(task)
    is_pinned = bool(getattr(task, "pinned", False))

    chips: list[ft.Control] = [
        ft.Container(
            content=ft.Text(
                STATUS_LABELS.get(task.status, task.status),
                size=11,
                color=status_color,
                weight=ft.FontWeight.W_500,
            ),
            bgcolor=f"{status_color}22",
            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            border_radius=ft.BorderRadius.all(12),
            on_click=lambda e, tid=task.id: (
                on_cycle_status(tid) if on_cycle_status else None
            ),
        ),
        ft.Text(
            due,
            size=11,
            color=due_color,
            weight=ft.FontWeight.W_600 if (overdue or due_today or due_kind == "soon") else None,
        ),
    ]
    if due_today:
        chips.insert(
            1,
            ft.Container(
                content=ft.Text("сегодня", size=10, color=ORANGE, weight=ft.FontWeight.W_700),
                bgcolor="#FF8A0022",
                padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                border_radius=ft.BorderRadius.all(10),
            ),
        )
    if tag and tag_color:
        chips.append(
            ft.Container(
                content=ft.Text(tag, size=10, color=tag_color),
                bgcolor=f"{tag_color}22",
                padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                border_radius=ft.BorderRadius.all(10),
            )
        )
    if progress is not None:
        d, tot = progress
        chips.append(
            ft.Container(
                content=ft.Text(
                    f"{d}/{tot}",
                    size=10,
                    color=GREEN if d >= tot else MUTED,
                    weight=ft.FontWeight.W_700,
                ),
                bgcolor="#3DDC9722" if d >= tot else "#2A2A32",
                padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                border_radius=ft.BorderRadius.all(10),
            )
        )
    em = getattr(task, "estimated_min", None)
    if em is not None:
        try:
            em_i = int(em)
        except (TypeError, ValueError):
            em_i = 0
        if em_i > 0:
            chips.append(
                ft.Container(
                    content=ft.Text(
                        f"⏱ {em_i}м",
                        size=10,
                        color=MUTED,
                        weight=ft.FontWeight.W_600,
                    ),
                    bgcolor="#2A2A32",
                    padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                    border_radius=ft.BorderRadius.all(10),
                )
            )
    chips.append(ft.Container(expand=True))
    chips.append(
        ft.Text(
            PRIORITY_LABELS.get(task.priority, task.priority),
            size=10,
            color=pri_color,
            weight=ft.FontWeight.W_600,
        )
    )

    border_color = RED if overdue else (ORANGE if due_today or is_pinned else "#2A2A32")

    def _tap(_):
        if select_mode and on_toggle_select:
            on_toggle_select(task.id)
        elif on_tap:
            on_tap(task.id)

    leading: list[ft.Control] = []
    if select_mode:
        leading.append(
            ft.Checkbox(
                value=selected,
                fill_color=ORANGE,
                check_color="#0F0F12",
            )
        )
    leading.append(ft.Container(width=3, height=36, bgcolor=pri_color, border_radius=2))

    trailing: list[ft.Control] = []
    if not select_mode:
        if on_toggle_pin:
            trailing.append(
                ft.IconButton(
                    icon=ft.Icons.PUSH_PIN if is_pinned else ft.Icons.PUSH_PIN_OUTLINED,
                    icon_size=18,
                    icon_color=ORANGE if is_pinned else MUTED,
                    tooltip="Открепить" if is_pinned else "Закрепить",
                    on_click=lambda e, tid=task.id, p=is_pinned: on_toggle_pin(tid, not p),
                )
            )
        trailing.append(
            ft.IconButton(
                icon=ft.Icons.DELETE_OUTLINE,
                icon_size=18,
                icon_color=MUTED,
                tooltip="Удалить",
                on_click=lambda e, tid=task.id: on_delete(tid) if on_delete else None,
            )
        )

    style = card_style(accent=overdue or due_today or (select_mode and selected))
    style["border"] = ft.Border.all(
        1, ORANGE if (select_mode and selected) else border_color
    )

    def _long_press(_):
        if select_mode:
            return
        if on_toggle_pin:
            on_toggle_pin(task.id, not is_pinned)

    return ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        *leading,
                        ft.Column(
                            [
                                ft.Row(
                                    [
                                        *(
                                            [
                                                ft.Icon(
                                                    ft.Icons.PUSH_PIN,
                                                    size=14,
                                                    color=ORANGE,
                                                )
                                            ]
                                            if is_pinned
                                            else []
                                        ),
                                        ft.Text(
                                            task.title,
                                            size=14,
                                            weight=ft.FontWeight.W_600,
                                            color=TEXT,
                                            expand=True,
                                        ),
                                    ],
                                    spacing=4,
                                ),
                                ft.Text(
                                    (task.description or "")[:72]
                                    + ("…" if len(task.description or "") > 72 else ""),
                                    size=11,
                                    color=MUTED,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        *trailing,
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(chips, spacing=8),
            ],
            spacing=10,
        ),
        padding=10 if compact else 14,
        **style,
        on_click=_tap if on_tap else None,
        on_long_press=_long_press if on_toggle_pin else None,
        ink=True,
        animate=_ANIM,
    )


def goal_card(
    goal: Goal,
    *,
    on_tap=None,
    on_add_progress=None,
    streak: int | None = None,
    compact: bool = False,
) -> ft.Control:
    pct = goal.percent_complete

    def _tap(_):
        if on_tap:
            on_tap(goal.id)

    streak_badge = None
    if streak is not None and streak > 0:
        streak_badge = ft.Container(
            content=ft.Row(
                [
                    ft.Text("🔥", size=11),
                    ft.Text(f"{streak}", size=11, weight=ft.FontWeight.W_700, color=ORANGE),
                ],
                spacing=2,
                tight=True,
            ),
            bgcolor="#FF8A0022",
            padding=ft.Padding.symmetric(horizontal=8, vertical=3),
            border_radius=ft.BorderRadius.all(10),
        )

    bar_w = max(4, 160 * pct / 100)
    return ft.Container(
        content=ft.Row(
            [
                mini_ring(pct, color=ORANGE if pct < 100 else GREEN, size=48),
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(goal.title, size=14, weight=ft.FontWeight.W_600, color=TEXT, expand=True),
                                *([streak_badge] if streak_badge else []),
                            ],
                            spacing=6,
                        ),
                        ft.Text(
                            f"{goal.current_value:g}/{goal.target_value:g} {goal.unit} · {goal.daily_quota:g}/день",
                            size=11,
                            color=MUTED,
                        ),
                        ft.Container(
                            content=ft.Container(
                                bgcolor=ORANGE,
                                width=bar_w,
                                height=4,
                                border_radius=2,
                                animate=_ANIM,
                            ),
                            bgcolor="#2A2A32",
                            height=4,
                            width=160,
                            border_radius=2,
                        ),
                    ],
                    spacing=6,
                    expand=True,
                ),
                ft.Container(
                    content=ft.Icon(ft.Icons.ADD_ROUNDED, size=18, color="#0F0F12"),
                    bgcolor=ORANGE,
                    width=36,
                    height=36,
                    border_radius=ft.BorderRadius.all(10),
                    alignment=ft.Alignment.CENTER,
                    on_click=lambda e, gid=goal.id: (
                        on_add_progress(gid) if on_add_progress else None
                    ),
                    ink=True,
                ),
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=10 if compact else 14,
        **card_style(),
        on_click=_tap if on_tap else None,
        ink=True,
        animate=_ANIM,
    )


def today_quota_card(
    item: dict,
    *,
    on_tap=None,
    on_quick_log=None,
    on_quick_fill=None,
    streak: int = 0,
    compact: bool = False,
) -> ft.Control:
    goal = item["goal"]
    today = item["today"]
    quota = item["quota"]
    complete = item["complete"]
    ratio = item["ratio"]
    remaining = max(0.0, float(quota) - float(today))
    pct = int(round(max(0.0, min(1.0, float(ratio))) * 100))
    accent = GREEN if complete else ORANGE
    left_bar = ft.Container(
        width=4,
        bgcolor=accent,
        border_radius=2,
        animate=_ANIM,
    )

    status_chip = ft.Container(
        content=ft.Text(
            "✓ Квота закрыта" if complete else "нужно ещё",
            size=11,
            color=accent,
            weight=ft.FontWeight.W_700,
        ),
        bgcolor=f"{accent}22",
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
        border_radius=ft.BorderRadius.all(12),
    )

    header_chips: list[ft.Control] = [status_chip]
    if streak and streak > 0:
        header_chips.insert(
            0,
            ft.Container(
                content=ft.Row(
                    [
                        ft.Text("🔥", size=11),
                        ft.Text(str(streak), size=11, weight=ft.FontWeight.W_700, color=ORANGE),
                    ],
                    spacing=2,
                    tight=True,
                ),
                bgcolor="#FF8A0022",
                padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                border_radius=ft.BorderRadius.all(10),
            ),
        )

    detail_bits = [f"Сегодня: {today:g} / {quota:g} {goal.unit}"]
    remaining_line = None
    if complete:
        remaining_line = ft.Text("Квота закрыта", size=12, color=GREEN, weight=ft.FontWeight.W_700)
    elif remaining > 0:
        remaining_line = ft.Text(
            f"Осталось {remaining:g} {goal.unit}",
            size=12,
            color=ORANGE,
            weight=ft.FontWeight.W_700,
        )

    bar_inner_w = max(4.0, 260.0 * max(0.0, min(1.0, float(ratio))))
    # Progress fill: ORANGE while open, GREEN when closed
    bar_color = GREEN if complete else ORANGE

    action_btns: list[ft.Control] = []
    if not complete and on_quick_fill:
        action_btns.append(
            ft.Container(
                content=ft.Text(
                    "+квота",
                    size=12,
                    weight=ft.FontWeight.W_700,
                    color="#0F0F12",
                ),
                bgcolor=GREEN,
                padding=ft.Padding.symmetric(horizontal=14, vertical=8),
                border_radius=ft.BorderRadius.all(14),
                on_click=lambda e, gid=goal.id: on_quick_fill(gid),
                ink=True,
                tooltip=f"Добавить ещё {remaining:g}" if remaining > 0 else "Добавить 1",
            )
        )
    action_btns.append(
        ft.Container(
            content=ft.Text(
                "+ лог",
                size=12,
                weight=ft.FontWeight.W_700,
                color="#0F0F12",
            ),
            bgcolor=ORANGE,
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            border_radius=ft.BorderRadius.all(14),
            on_click=lambda e, gid=goal.id: (
                on_quick_log(gid) if on_quick_log else None
            ),
            ink=True,
        )
    )
    action_btns.append(ft.Container(expand=True))
    action_btns.append(
        ft.TextButton(
            "Открыть",
            on_click=lambda e, gid=goal.id: on_tap(gid) if on_tap else None,
        )
    )

    # Soft green when complete — no aggressive orange border
    style = card_style(accent=False if complete else True)
    if complete:
        style["border"] = ft.Border.all(1, f"{GREEN}66")

    return ft.Container(
        content=ft.Row(
            [
                left_bar,
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(
                                    goal.title,
                                    size=14,
                                    weight=ft.FontWeight.W_700,
                                    color=TEXT,
                                    expand=True,
                                ),
                                *header_chips,
                            ],
                            spacing=6,
                        ),
                        ft.Text(" · ".join(detail_bits), size=12, color=MUTED),
                        *( [remaining_line] if remaining_line is not None else [] ),
                        ft.Row(
                            [
                                ft.Container(
                                    content=ft.Container(
                                        bgcolor=bar_color,
                                        width=bar_inner_w,
                                        height=8,
                                        border_radius=4,
                                        animate=_ANIM,
                                    ),
                                    bgcolor="#2A2A32",
                                    height=8,
                                    border_radius=4,
                                    expand=True,
                                ),
                                ft.Text(
                                    f"{pct}%",
                                    size=11,
                                    weight=ft.FontWeight.W_700,
                                    color=accent,
                                ),
                            ],
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Row(action_btns),
                    ],
                    spacing=8,
                    expand=True,
                ),
            ],
            spacing=10,
        ),
        padding=10 if compact else 14,
        **style,
        on_click=lambda e, gid=goal.id: on_tap(gid) if on_tap else None,
        ink=True,
        animate=_ANIM,
    )


def streak_badge_chip(title: str, streak: int, *, today_ok: bool = False) -> ft.Control:
    return ft.Container(
        content=ft.Column(
            [
                ft.Text("🔥" if streak > 0 else "💤", size=18),
                ft.Text(f"{streak} дн.", size=16, weight=ft.FontWeight.W_700, color=ORANGE if streak else MUTED),
                ft.Text(title[:16], size=10, color=MUTED, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(
                    "сегодня ✓" if today_ok else "сегодня ·",
                    size=10,
                    color=GREEN if today_ok else MUTED,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
        ),
        padding=12,
        expand=True,
        **card_style(accent=streak > 0),
        animate=_ANIM,
    )



def week_activity_strip(days: list, *, labels: bool = True) -> ft.Control:
    """7-day mini activity dots (last week of heatmap or dedicated list)."""
    if not days:
        return empty_illus("Нет данных", emoji="📊")
    # Prefer last 7 entries
    week = list(days[-7:]) if len(days) >= 7 else list(days)
    max_c = max((getattr(d, "count", 0) for d in week), default=0) or 1
    wd = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

    def _color(count: int) -> str:
        if count <= 0:
            return "#1C1C22"
        ratio = count / max_c
        if ratio < 0.34:
            return "#3D2200"
        if ratio < 0.67:
            return "#CC6E00"
        return ORANGE

    dots: list[ft.Control] = []
    for d in week:
        count = int(getattr(d, "count", 0) or 0)
        day = getattr(d, "day", None)
        label = wd[day.weekday()] if day is not None else "·"
        tip = f"{day.isoformat()}: {count}" if day is not None else str(count)
        col_items: list[ft.Control] = [
            ft.Container(
                width=14,
                height=14,
                bgcolor=_color(count),
                border_radius=7,
                tooltip=tip,
            )
        ]
        if labels:
            col_items.append(ft.Text(label, size=9, color=MUTED))
            if count:
                col_items.append(
                    ft.Text(str(count), size=9, color=TEXT, weight=ft.FontWeight.W_600)
                )
        dots.append(
            ft.Column(
                col_items,
                spacing=3,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
            )
        )
    return ft.Column(
        [
            ft.Text("Неделя", size=11, color=MUTED),
            ft.Row(dots, spacing=4),
        ],
        spacing=6,
    )


def heatmap_grid(days: list, *, week_starts_monday: bool = True) -> ft.Control:
    """GitHub-style contribution grid; days is list of HeatmapDay-like with .day .count."""
    if not days:
        return empty_illus("Нет данных", emoji="🗓️")

    max_c = max((d.count for d in days), default=0)
    max_c = max(max_c, 1)

    def cell_color(count: int) -> str:
        if count <= 0:
            return "#1C1C22"
        ratio = count / max_c
        # Derive intensity from live accent
        base = ORANGE.lstrip("#")
        if len(base) == 6:
            r, g, b = int(base[0:2], 16), int(base[2:4], 16), int(base[4:6], 16)
        else:
            r, g, b = 255, 138, 0

        def mix(f: float) -> str:
            # darken toward charcoal
            rr = int(r * f + 28 * (1 - f))
            gg = int(g * f + 28 * (1 - f))
            bb = int(b * f + 34 * (1 - f))
            return f"#{rr:02X}{gg:02X}{bb:02X}"

        if ratio < 0.25:
            return mix(0.25)
        if ratio < 0.5:
            return mix(0.45)
        if ratio < 0.75:
            return mix(0.7)
        return ORANGE

    # Pad to align columns by weekday
    first = days[0].day
    # Monday=0 … Sunday=6 if week_starts_monday else Sunday=0
    if week_starts_monday:
        pad = first.weekday()  # Mon=0
    else:
        pad = (first.weekday() + 1) % 7  # Sun=0

    cells: list[ft.Control] = []
    for _ in range(pad):
        cells.append(ft.Container(width=12, height=12))

    for d in days:
        tip = f"{d.day.isoformat()}: {d.count}"
        cells.append(
            ft.Container(
                width=12,
                height=12,
                bgcolor=cell_color(d.count),
                border_radius=2,
                tooltip=tip,
            )
        )

    # Arrange into columns of 7 (weeks as columns)
    cols: list[ft.Control] = []
    col_cells: list[ft.Control] = []
    for i, c in enumerate(cells):
        col_cells.append(c)
        if len(col_cells) == 7:
            cols.append(ft.Column(col_cells, spacing=3))
            col_cells = []
    if col_cells:
        while len(col_cells) < 7:
            col_cells.append(ft.Container(width=12, height=12))
        cols.append(ft.Column(col_cells, spacing=3))

    legend = ft.Row(
        [
            ft.Text("Меньше", size=9, color=MUTED),
            ft.Container(width=10, height=10, bgcolor="#1C1C22", border_radius=2),
            ft.Container(width=10, height=10, bgcolor="#3D2200", border_radius=2),
            ft.Container(width=10, height=10, bgcolor="#7A4500", border_radius=2),
            ft.Container(width=10, height=10, bgcolor="#CC6E00", border_radius=2),
            ft.Container(width=10, height=10, bgcolor=ORANGE, border_radius=2),
            ft.Text("Больше", size=9, color=MUTED),
        ],
        spacing=4,
        alignment=ft.MainAxisAlignment.END,
    )

    return ft.Column(
        [
            ft.Row(cols, spacing=3, scroll=ft.ScrollMode.AUTO),
            legend,
        ],
        spacing=10,
    )


def stat_tile(label: str, value: str, *, accent: str = ORANGE) -> ft.Control:
    return ft.Container(
        content=ft.Column(
            [
                ft.Text(label, size=11, color=MUTED),
                ft.Text(value, size=20, weight=ft.FontWeight.W_700, color=TEXT),
                ft.Container(height=3, width=28, bgcolor=accent, border_radius=2),
            ],
            spacing=6,
        ),
        padding=14,
        expand=True,
        **card_style(),
        animate=_ANIM,
    )
