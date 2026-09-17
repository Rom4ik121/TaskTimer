"""Focus / Pomodoro timer screen."""
from __future__ import annotations

import asyncio

import flet as ft

from app.db import get_session
from app.schemas import SettingsUpdate, TimeSessionCreate, TimeSessionUpdate
from app.services import analytics_service, settings_service, task_service, timer_service
from app.ui.components.dialogs import show_snack
from app.ui.components.cards import empty_state
from app.ui.theme import BORDER, GREEN, MUTED, ORANGE, TEXT, card_style, muted


def _fmt(sec: int) -> str:
    sec = max(0, int(sec))
    m, s = divmod(sec, 60)
    return f"{m:02d}:{s:02d}"


PRESETS = [
    ("Помодоро 25", 25 * 60),
    ("Перерыв 5", 5 * 60),
    ("Глубокий 50", 50 * 60),
    ("15 мин", 15 * 60),
]
# Quick work/break pair chips (persist to settings): 15/5, 50/10
PAIR_PRESETS = [("15/5", 15, 5), ("50/10", 50, 10)]


def build_focus(page: ft.Page, *, on_back, refresh_all, on_open_note=None) -> ft.Control:
    body = ft.Column(spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)
    state = {"sid": None, "ticking": False, "generation": 0, "note": "", "note_sid": None, "hist_filter": "all"}

    def stop_ticker():
        state["ticking"] = False
        state["generation"] += 1

    def start_ticker():
        stop_ticker()
        state["ticking"] = True
        gen = state["generation"]

        async def loop():
            while state["ticking"] and state["generation"] == gen:
                await asyncio.sleep(1)
                if not state["ticking"] or state["generation"] != gen:
                    break
                if state["sid"] is None:
                    break
                with get_session() as session:
                    ts = timer_service.tick(session, state["sid"])
                    if not ts or ts.status != "running":
                        state["ticking"] = False
                        if ts and ts.status == "done":
                            note = (state.get("note") or "").strip()
                            timer_service.complete(session, ts.id, note=note)
                            show_snack(page, "Сессия завершена" + (f" · {note[:40]}" if note else ""))
                        reload()
                        return
                reload()

        try:
            page.run_task(loop)
        except Exception:
            pass

    def reload(_: ft.ControlEvent | None = None):
        body.controls.clear()
        with get_session() as session:
            active = timer_service.get_active_session(session)
            if active and active.status == "running":
                active = timer_service.tick(session, active.id) or active
            hist_noted = (state.get("hist_filter") or "all") == "noted"
            history = timer_service.list_sessions(
                session, limit=20, has_note=True if hist_noted else None
            )
            tasks = task_service.list_tasks(session)
            task_map = {t.id: t.title for t in tasks}
            settings = settings_service.get_settings(session)
            default_work = max(5, min(90, int(settings.pomodoro_work_min))) * 60
            default_break = max(1, min(30, int(settings.pomodoro_break_min))) * 60
            week = analytics_service.weekly_focus_stats(session, days=7)

        if active:
            state["sid"] = active.id
            if state.get("note_sid") != active.id:
                db_note = (getattr(active, "note", None) or "").strip()
                if db_note:
                    state["note"] = db_note
                # else keep in-progress draft across preset / new session
                state["note_sid"] = active.id
        elif state.get("sid") is None and state.get("note_sid") is not None:
            state["note"] = ""
            state["note_sid"] = None

        display = active
        remaining = display.remaining_sec if display else default_work
        status = display.status if display else "paused"
        label = display.label if display else "Фокус"
        duration = display.duration_sec if display else default_work
        linked = ""
        if display and display.task_id:
            linked = task_map.get(display.task_id, f"#{display.task_id}")

        ring_val = 0.0 if duration <= 0 else max(0.0, min(1.0, remaining / duration))
        status_ru = {"running": "Идёт", "paused": "Пауза", "done": "Готово"}.get(status, status)

        clock = ft.Container(
            content=ft.Column(
                [
                    muted(label),
                    ft.Text(_fmt(remaining), size=48, weight=ft.FontWeight.W_700, color=TEXT),
                    ft.Text(status_ru, size=14, color=ORANGE if status == "running" else MUTED),
                    ft.ProgressBar(value=ring_val, color=ORANGE, bgcolor="#2A2A32", bar_height=8),
                    *([muted(f"Задача: {linked}")] if linked else []),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            padding=20,
            **card_style(accent=True),
            alignment=ft.Alignment.CENTER,
        )

        def ensure_session(duration_sec: int | None = None, label_text: str | None = None):
            with get_session() as session:
                active_s = timer_service.get_active_session(session)
                if active_s and duration_sec is None:
                    return active_s.id
                data = TimeSessionCreate(
                    label=label_text or (active_s.label if active_s else "Фокус"),
                    duration_sec=duration_sec
                    or (active_s.duration_sec if active_s else default_work),
                    task_id=active_s.task_id if active_s else None,
                )
                ts = timer_service.create_session(session, data)
                return ts.id

        def on_play(_):
            sid = ensure_session()
            with get_session() as session:
                timer_service.play(session, sid)
            state["sid"] = sid
            start_ticker()
            reload()

        def on_pause(_):
            if state["sid"] is None:
                return
            with get_session() as session:
                timer_service.pause(session, state["sid"])
            stop_ticker()
            reload()

        def on_reset(_):
            sid = state["sid"] or ensure_session()
            with get_session() as session:
                timer_service.reset(session, sid)
            state["sid"] = sid
            stop_ticker()
            reload()

        def on_done(_):
            sid = state["sid"] or ensure_session()
            note = (state.get("note") or "").strip()
            with get_session() as session:
                timer_service.complete(session, sid, note=note)
            stop_ticker()
            state["sid"] = None
            state["note"] = ""
            state["note_sid"] = None
            show_snack(page, "Сессия сохранена" + (f" · заметка" if note else ""))
            reload()

        def on_note_change(e):
            state["note"] = e.control.value or ""

        def on_note_blur(_e=None):
            sid = state.get("sid")
            if sid is None:
                return
            note = (state.get("note") or "").strip()
            with get_session() as session:
                timer_service.update_session(
                    session, sid, TimeSessionUpdate(note=note)
                )

        def use_preset(name: str, secs: int):
            def _(_e=None):
                sid = ensure_session(duration_sec=secs, label_text=name)
                with get_session() as session:
                    timer_service.reset(session, sid)
                state["sid"] = sid
                stop_ticker()
                show_snack(page, f"Режим: {name}")
                reload()

            return _

        def link_task(_):
            with get_session() as session:
                tasks_list = task_service.list_tasks(session)
            opts = [ft.dropdown.Option("", "Без задачи")] + [
                ft.dropdown.Option(str(t.id), t.title[:40]) for t in tasks_list[:40]
            ]
            dd = ft.Dropdown(
                label="Задача",
                options=opts,
                value="",
                border_color=BORDER,
                focused_border_color=ORANGE,
                color=TEXT,
            )

            def submit(__):
                sid = ensure_session()
                tid = int(dd.value) if dd.value else None
                with get_session() as session:
                    timer_service.update_session(
                        session, sid, TimeSessionUpdate(task_id=tid)
                    )
                page.pop_dialog()
                reload()

            page.show_dialog(
                ft.AlertDialog(
                    title=ft.Text("Привязать задачу", color=TEXT),
                    content=dd,
                    actions=[
                        ft.TextButton("Отмена", on_click=lambda e: page.pop_dialog()),
                        ft.TextButton("ОК", on_click=submit),
                    ],
                )
            )

        controls = ft.Row(
            [
                ft.Container(
                    content=ft.Icon(ft.Icons.PLAY_ARROW_ROUNDED, color="#0F0F12", size=28),
                    bgcolor=ORANGE,
                    width=56,
                    height=56,
                    border_radius=28,
                    alignment=ft.Alignment.CENTER,
                    on_click=on_play,
                    ink=True,
                ),
                ft.Container(
                    content=ft.Icon(ft.Icons.PAUSE_ROUNDED, color=TEXT, size=28),
                    bgcolor="#2A2A32",
                    width=56,
                    height=56,
                    border_radius=28,
                    alignment=ft.Alignment.CENTER,
                    on_click=on_pause,
                    ink=True,
                ),
                ft.Container(
                    content=ft.Icon(ft.Icons.REPLAY_ROUNDED, color=TEXT, size=26),
                    bgcolor="#2A2A32",
                    width=56,
                    height=56,
                    border_radius=28,
                    alignment=ft.Alignment.CENTER,
                    on_click=on_reset,
                    ink=True,
                ),
                ft.Container(
                    content=ft.Icon(ft.Icons.CHECK_ROUNDED, color="#0F0F12", size=26),
                    bgcolor=GREEN,
                    width=56,
                    height=56,
                    border_radius=28,
                    alignment=ft.Alignment.CENTER,
                    on_click=on_done,
                    ink=True,
                    tooltip="Завершить с заметкой",
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=16,
        )

        note_field = ft.TextField(
            label="Заметка сессии",
            hint_text="Опционально — сохранится при завершении",
            value=state.get("note") or "",
            multiline=True,
            min_lines=1,
            max_lines=3,
            border_color=BORDER,
            focused_border_color=ORANGE,
            color=TEXT,
            on_change=on_note_change,
            on_blur=on_note_blur,
        )

        def use_pair(work_m: int, break_m: int):
            """Quick work/break pair chip — sets timer + persists settings."""
            def _(_e=None):
                w = max(5, min(90, int(work_m)))
                b = max(1, min(30, int(break_m)))
                with get_session() as session:
                    settings_service.update_settings(
                        session,
                        SettingsUpdate(
                            pomodoro_work_min=w,
                            pomodoro_break_min=b,
                        ),
                    )
                name = f"{w}/{b}"
                sid = ensure_session(duration_sec=w * 60, label_text=f"Помодоро {w}")
                with get_session() as session:
                    timer_service.reset(session, sid)
                state["sid"] = sid
                stop_ticker()
                show_snack(page, f"Пресет {name} · работа {w} / перерыв {b}")
                reload()

            return _

        live_presets = [
            (f"Помодоро {default_work // 60}", default_work),
            (f"Перерыв {default_break // 60}", default_break),
            ("Глубокий 50", 50 * 60),
            ("15 мин", 15 * 60),
        ]
        presets = ft.Row(
            [
                *[
                    ft.Container(
                        content=ft.Text(name, size=11, color=TEXT),
                        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                        border=ft.Border.all(1, BORDER),
                        border_radius=ft.BorderRadius.all(14),
                        on_click=use_preset(name, secs),
                        ink=True,
                    )
                    for name, secs in live_presets
                ],
                *[
                    ft.Container(
                        content=ft.Text(label, size=11, weight=ft.FontWeight.W_700, color=ORANGE),
                        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                        border=ft.Border.all(1, ORANGE),
                        border_radius=ft.BorderRadius.all(14),
                        on_click=use_pair(wm, bm),
                        ink=True,
                        tooltip=f"Работа {wm} мин · перерыв {bm} мин",
                    )
                    for label, wm, bm in PAIR_PRESETS
                ],
            ],
            wrap=True,
            spacing=8,
            run_spacing=8,
        )

        def _hist_chip(label: str, mode: str) -> ft.Container:
            active = (state.get("hist_filter") or "all") == mode

            def _on(_e=None, m=mode):
                state["hist_filter"] = m
                reload()

            return ft.Container(
                content=ft.Text(
                    label,
                    size=12,
                    color="#0F0F12" if active else MUTED,
                    weight=ft.FontWeight.W_500,
                ),
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                border_radius=ft.BorderRadius.all(16),
                bgcolor=ORANGE if active else "transparent",
                border=ft.Border.all(1, ORANGE if active else BORDER),
                on_click=_on,
                ink=True,
            )

        hist_chips = ft.Row(
            [
                _hist_chip("Все", "all"),
                _hist_chip("С заметкой", "noted"),
            ],
            spacing=8,
        )

        hist_items = []
        status_ru_map = {"running": "Идёт", "paused": "Пауза", "done": "Готово"}
        for h in history:
            spent = max(0, int(h.duration_sec or 0) - int(h.remaining_sec or 0))
            if h.status == "done":
                dur_txt = _fmt(spent or h.duration_sec)
            elif h.status == "running":
                dur_txt = f"{_fmt(h.remaining_sec)} ост. / {_fmt(h.duration_sec)}"
            else:
                dur_txt = f"{_fmt(h.remaining_sec)} / {_fmt(h.duration_sec)}"
            st_ru = status_ru_map.get(h.status, h.status)
            note_txt = (getattr(h, "note", None) or "").strip()
            row_lines = [
                ft.Text(
                    h.label or "Фокус",
                    size=13,
                    weight=ft.FontWeight.W_600,
                    color=TEXT,
                ),
                ft.Text(
                    f"{dur_txt} · {st_ru}",
                    size=11,
                    color=MUTED,
                ),
            ]
            if note_txt:
                row_lines.append(
                    ft.Text(
                        note_txt,
                        size=12,
                        color=ORANGE,
                        max_lines=4,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    )
                )
            hist_items.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Column(
                                row_lines,
                                spacing=2,
                                expand=True,
                            ),
                            ft.Container(
                                width=8,
                                height=8,
                                bgcolor=ORANGE
                                if h.status == "running"
                                else (GREEN if h.status == "done" else MUTED),
                                border_radius=4,
                            ),
                        ]
                    ),
                    padding=12,
                    **card_style(),
                )
            )

        def go_back(_):
            stop_ticker()
            on_back()

        header = ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK_IOS_NEW,
                    icon_color=TEXT,
                    icon_size=18,
                    on_click=go_back,
                ),
                ft.Text("Фокус", size=22, weight=ft.FontWeight.W_700, color=TEXT, expand=True),
                ft.IconButton(
                    icon=ft.Icons.DESCRIPTION_OUTLINED,
                    icon_color=ORANGE,
                    icon_size=20,
                    tooltip="Заметка · focus.md",
                    on_click=lambda e: on_open_note("focus.md", "Фокус") if on_open_note else None,
                ),
                ft.TextButton("Задача", on_click=link_task),
            ]
        )


        hrs = week.total_sec // 3600
        mins = (week.total_sec % 3600) // 60
        focus_time = f"{hrs}ч {mins}м" if hrs else f"{mins}м"
        week_tile = ft.Container(
            content=ft.Row(
                [
                    ft.Column(
                        [
                            muted("Неделя"),
                            ft.Text(focus_time, size=18, weight=ft.FontWeight.W_700, color=ORANGE),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.Column(
                        [
                            muted("Сессий"),
                            ft.Text(str(week.sessions_count), size=18, weight=ft.FontWeight.W_700, color=TEXT),
                        ],
                        spacing=2,
                        horizontal_alignment=ft.CrossAxisAlignment.END,
                    ),
                ]
            ),
            padding=14,
            **card_style(),
        )
        body.controls.extend(
            [
                header,
                week_tile,
                clock,
                controls,
                note_field,
                muted("Пресеты"),
                presets,
                ft.Text("История · 20", size=16, weight=ft.FontWeight.W_600, color=TEXT),
                hist_chips,
                *(
                    hist_items
                    or [
                        empty_state(
                            "Нет сессий с заметкой"
                            if (state.get("hist_filter") or "all") == "noted"
                            else "Пока нет сессий",
                            "Завершите фокус с текстом"
                            if (state.get("hist_filter") or "all") == "noted"
                            else "Запустите помодоро",
                            emoji="📝"
                            if (state.get("hist_filter") or "all") == "noted"
                            else "⏱️",
                        )
                    ]
                ),
                ft.Container(height=8),
            ]
        )
        page.update()

        if status == "running" and not state["ticking"]:
            start_ticker()

    reload()
    return ft.Container(
        content=body,
        padding=ft.Padding.only(left=16, right=16, top=18, bottom=8),
        expand=True,
    )
