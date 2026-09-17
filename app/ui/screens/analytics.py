"""Analytics: status distribution + 14-day line + streaks + heatmap + weekly review."""
from __future__ import annotations

import flet as ft
import flet_charts as fc

from app.db import get_session
from app.services import analytics_service, goal_service, settings_service, streak_service
from app.ui.components.cards import heatmap_grid, streak_badge_chip
from app.ui.components.progress_ring import donut_progress
from app.ui.components.cards import empty_illus
from app.ui.components.dialogs import show_snack
from app.ui.theme import (
    BLUE,
    BORDER,
    CARD,
    GREEN,
    MUTED,
    ORANGE,
    PURPLE,
    TEXT,
    card_style,
    muted,
)


def build_analytics(page: ft.Page, *, refresh_all=None, on_open_focus=None, on_open_note=None) -> ft.Control:
    root_col = ft.Column(spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)

    def reload(_: ft.ControlEvent | None = None):
        root_col.controls.clear()
        with get_session() as session:
            dist = analytics_service.status_distribution(session)
            points = analytics_service.completed_last_n_days(session, 14)
            goals = goal_service.list_goals(session)
            stats = analytics_service.overview_stats(session)
            streaks = streak_service.all_streaks(session)
            heatmap = analytics_service.activity_heatmap(session, weeks=14)
            settings = settings_service.get_settings(session)
            focus = analytics_service.weekly_focus_stats(session, days=7)
            forecasts = analytics_service.goal_forecasts(session)
            review = analytics_service.weekly_review(
                session, week_starts_monday=settings.week_starts_monday
            )
            week_done, week_target = analytics_service.weekly_goal_progress(session)
            focus_notes = analytics_service.recent_focus_notes(session, limit=5)

        pie = fc.PieChart(
            sections=[
                fc.PieChartSection(
                    value=max(dist.todo, 0.001), color=MUTED, radius=18, title=f"{dist.todo}"
                ),
                fc.PieChartSection(
                    value=max(dist.in_progress, 0.001),
                    color=ORANGE,
                    radius=18,
                    title=f"{dist.in_progress}",
                ),
                fc.PieChartSection(
                    value=max(dist.done, 0.001), color=GREEN, radius=18, title=f"{dist.done}"
                ),
            ],
            sections_space=2,
            center_space_color=CARD,
            center_space_radius=42,
            width=160,
            height=160,
        )

        max_y = max((p.completed for p in points), default=1)
        max_y = max(max_y, 1)
        series = fc.LineChartData(
            curved=True,
            color=ORANGE,
            stroke_width=2.5,
            rounded_stroke_cap=True,
            below_line_bgcolor="#FF8A0033",
            points=[fc.LineChartDataPoint(x=i, y=p.completed) for i, p in enumerate(points)],
        )
        labels = [
            fc.ChartAxisLabel(
                value=i,
                label=ft.Text(p.day.strftime("%d"), size=9, color=MUTED),
            )
            for i, p in enumerate(points)
            if i % 2 == 0
        ]
        line = fc.LineChart(
            data_series=[series],
            min_y=0,
            max_y=max_y + 1,
            min_x=0,
            max_x=13,
            bgcolor=CARD,
            border=ft.Border.all(0, "transparent"),
            horizontal_grid_lines=fc.ChartGridLines(color="#2A2A32", width=1),
            vertical_grid_lines=fc.ChartGridLines(color="#1A1A20", width=1),
            bottom_axis=fc.ChartAxis(labels=labels, label_size=20),
            left_axis=fc.ChartAxis(label_size=28),
            height=200,
            expand=True,
        )

        goal_rings = ft.Row(
            [
                ft.Column(
                    [
                        donut_progress(g.percent_complete, size=88, thickness=10, color=c),
                        ft.Text(
                            g.title[:14],
                            size=10,
                            color=MUTED,
                            text_align=ft.TextAlign.CENTER,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=6,
                )
                for g, c in zip(goals[:3], [ORANGE, BLUE, PURPLE])
            ],
            alignment=ft.MainAxisAlignment.SPACE_AROUND,
        )

        streak_section = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        "Серии целей",
                        size=14,
                        weight=ft.FontWeight.W_600,
                        color=TEXT,
                    ),
                    ft.Row(
                        [
                            streak_badge_chip(s.title, s.current_streak, today_ok=s.today_complete)
                            for s in streaks[:3]
                        ],
                        spacing=8,
                    )
                    if streaks
                    else empty_illus("Нет целей для серий", emoji="🔥"),
                ],
                spacing=12,
            ),
            padding=16,
            **card_style(),
        )


        focus_max = max((d.completed for d in focus.days), default=1) or 1
        wd = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
        bar_h = 56
        today = focus.days[-1].day if focus.days else None

        def _focus_bar(d):
            h = max(6, int(bar_h * (d.completed / focus_max))) if d.completed else 6
            fill_kw: dict = {
                "width": 22,
                "height": h,
                "border_radius": ft.BorderRadius.only(
                    top_left=8, top_right=8, bottom_left=4, bottom_right=4
                ),
            }
            if d.completed:
                fill_kw["gradient"] = ft.LinearGradient(
                    begin=ft.Alignment.BOTTOM_CENTER,
                    end=ft.Alignment.TOP_CENTER,
                    colors=["#FF8A00", "#FFB347"],
                )
            else:
                fill_kw["bgcolor"] = "#2A2A32"
            is_today = today is not None and d.day == today
            return ft.Column(
                [
                    ft.Container(
                        content=ft.Container(**fill_kw),
                        width=28,
                        height=bar_h,
                        alignment=ft.Alignment(0, 1),
                        bgcolor="#16161C",
                        border_radius=ft.BorderRadius.all(10),
                        padding=ft.Padding.only(bottom=2),
                    ),
                    ft.Text(
                        wd[d.day.weekday()],
                        size=10,
                        color=ORANGE if is_today else MUTED,
                        weight=ft.FontWeight.W_600 if is_today else ft.FontWeight.W_400,
                    ),
                    ft.Text(
                        f"{d.completed}м" if d.completed else "·",
                        size=9,
                        color=TEXT if d.completed else MUTED,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=4,
                alignment=ft.MainAxisAlignment.END,
            )

        focus_bars = ft.Row(
            [_focus_bar(d) for d in focus.days],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.END,
        )
        hrs = focus.total_sec // 3600
        mins = (focus.total_sec % 3600) // 60
        focus_time = f"{hrs}ч {mins}м" if hrs else f"{mins}м"
        avg_min = (
            round(focus.total_min / focus.sessions_count)
            if focus.sessions_count
            else 0
        )
        focus_section = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.Icon(
                                    ft.Icons.TIMER_OUTLINED, color=ORANGE, size=18
                                ),
                                width=32,
                                height=32,
                                bgcolor="#2A1C12",
                                border_radius=ft.BorderRadius.all(10),
                                alignment=ft.Alignment.CENTER,
                            ),
                            ft.Column(
                                [
                                    ft.Text(
                                        "Фокус · неделя",
                                        size=15,
                                        weight=ft.FontWeight.W_700,
                                        color=TEXT,
                                    ),
                                    muted("Pomodoro и сессии за 7 дней"),
                                ],
                                spacing=1,
                                expand=True,
                            ),
                        ],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.Column(
                                    [
                                        ft.Text(
                                            focus_time,
                                            size=24,
                                            weight=ft.FontWeight.W_700,
                                            color=ORANGE,
                                        ),
                                        muted("всего"),
                                    ],
                                    spacing=2,
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                expand=True,
                                padding=10,
                                bgcolor="#16161C",
                                border_radius=ft.BorderRadius.all(12),
                            ),
                            ft.Container(
                                content=ft.Column(
                                    [
                                        ft.Text(
                                            str(focus.sessions_count),
                                            size=24,
                                            weight=ft.FontWeight.W_700,
                                            color=TEXT,
                                        ),
                                        muted("сессий"),
                                    ],
                                    spacing=2,
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                expand=True,
                                padding=10,
                                bgcolor="#16161C",
                                border_radius=ft.BorderRadius.all(12),
                            ),
                            ft.Container(
                                content=ft.Column(
                                    [
                                        ft.Text(
                                            f"{avg_min}м",
                                            size=24,
                                            weight=ft.FontWeight.W_700,
                                            color=BLUE,
                                        ),
                                        muted("среднее"),
                                    ],
                                    spacing=2,
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                expand=True,
                                padding=10,
                                bgcolor="#16161C",
                                border_radius=ft.BorderRadius.all(12),
                            ),
                        ],
                        spacing=8,
                    ),
                    focus_bars,
                ],
                spacing=14,
            ),
            padding=16,
            **card_style(accent=True),
        )

        def _tap_focus_note(snippet: str):
            if on_open_focus:
                on_open_focus()
                return
            # Fallback when navigation callback not wired
            async def _copy():
                try:
                    await page.clipboard.set(snippet)
                except Exception:
                    pass

            try:
                page.run_task(_copy)
            except Exception:
                pass
            show_snack(page, "Заметка скопирована")

        note_rows = []
        for sn in focus_notes:
            note_rows.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                sn.title,
                                size=13,
                                weight=ft.FontWeight.W_600,
                                color=TEXT,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.Text(
                                sn.note_snippet,
                                size=12,
                                color=ORANGE,
                                max_lines=2,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                        ],
                        spacing=2,
                    ),
                    padding=ft.Padding.symmetric(horizontal=4, vertical=6),
                    ink=True,
                    on_click=(
                        lambda e, snippet=sn.note_snippet: _tap_focus_note(snippet)
                    ),
                    tooltip="Открыть Фокус",
                )
            )
        focus_notes_section = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.Icon(
                                    ft.Icons.STICKY_NOTE_2_OUTLINED,
                                    color=ORANGE,
                                    size=18,
                                ),
                                width=32,
                                height=32,
                                bgcolor="#2A1C12",
                                border_radius=ft.BorderRadius.all(10),
                                alignment=ft.Alignment.CENTER,
                            ),
                            ft.Column(
                                [
                                    ft.Text(
                                        "Заметки фокуса",
                                        size=15,
                                        weight=ft.FontWeight.W_700,
                                        color=TEXT,
                                    ),
                                    muted("Последние 5 · нажмите — открыть Фокус"),
                                ],
                                spacing=1,
                                expand=True,
                            ),
                        ],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    *(
                        note_rows
                        if note_rows
                        else [empty_illus("Нет заметок сессий", emoji="📝")]
                    ),
                ],
                spacing=10,
            ),
            padding=16,
            **card_style(),
        )


        forecast_rows = []
        for f in forecasts:
            if f.days_to_complete is None:
                eta = "нет квоты"
                eta_color = MUTED
            elif f.days_to_complete == 0:
                eta = "готово 🎉"
                eta_color = GREEN
            else:
                eta = f"~{f.days_to_complete} дн."
                eta_color = ORANGE
            forecast_rows.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        f.title,
                                        size=13,
                                        weight=ft.FontWeight.W_600,
                                        color=TEXT,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                    muted(
                                        f"{f.percent_complete:.0f}% · осталось {f.remaining:g} {f.unit}"
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.Text(
                                eta,
                                size=13,
                                weight=ft.FontWeight.W_700,
                                color=eta_color,
                            ),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(horizontal=4, vertical=6),
                )
            )
        forecast_section = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        "Прогноз целей",
                        size=14,
                        weight=ft.FontWeight.W_600,
                        color=TEXT,
                    ),
                    muted("Дней до завершения при текущей квоте"),
                    *(
                        forecast_rows
                        if forecast_rows
                        else [empty_illus("Нет целей для прогноза", emoji="📅")]
                    ),
                ],
                spacing=10,
            ),
            padding=16,
            **card_style(),
        )

        heat_section = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        "Календарь активности",
                        size=14,
                        weight=ft.FontWeight.W_600,
                        color=TEXT,
                    ),
                    muted("Логи прогресса + завершённые задачи"),
                    heatmap_grid(heatmap, week_starts_monday=settings.week_starts_monday),
                ],
                spacing=10,
            ),
            padding=16,
            **card_style(),
        )

        period = (
            f"{review.week_start.strftime('%d.%m')}–{review.week_end.strftime('%d.%m.%Y')}"
        )

        def _review_tile(emoji: str, label: str, value: str, color: str) -> ft.Control:
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Text(emoji, size=18),
                        ft.Text(value, size=18, weight=ft.FontWeight.W_700, color=color),
                        ft.Text(label, size=11, color=MUTED),
                    ],
                    spacing=4,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                expand=True,
                padding=10,
                bgcolor="#1A1A22",
                border_radius=ft.BorderRadius.all(12),
                border=ft.Border.all(1, "#2A2A32"),
            )

        review_section = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        "Обзор недели",
                        size=14,
                        weight=ft.FontWeight.W_600,
                        color=TEXT,
                    ),
                    muted(f"Неделя {period}"),
                    ft.Row(
                        [
                            _review_tile("✅", "Завершено", str(review.completed_count), GREEN),
                            _review_tile("⏱️", "Фокус, мин", str(review.focus_min), BLUE),
                        ],
                        spacing=8,
                    ),
                    ft.Row(
                        [
                            _review_tile(
                                "🎯", "Квоты закрыты", str(review.quotas_met_days), ORANGE
                            ),
                            _review_tile("🔥", "Лучшая серия", str(review.best_streak), PURPLE),
                        ],
                        spacing=8,
                    ),
                ],
                spacing=10,
            ),
            padding=16,
            **card_style(),
        )

        def show_weekly_review(_=None):
            cards = [
                ("✅", "Задачи завершены", str(review.completed_count), GREEN),
                ("⏱️", "Фокус, минут", str(review.focus_min), BLUE),
                ("🎯", "Квоты (цель×день)", str(review.quotas_met_days), ORANGE),
                ("🔥", "Лучшая серия", str(review.best_streak), PURPLE),
            ]
            rows = []
            for emoji, label, value, color in cards:
                rows.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Text(emoji, size=22),
                                ft.Column(
                                    [
                                        ft.Text(
                                            label,
                                            size=12,
                                            color=MUTED,
                                        ),
                                        ft.Text(
                                            value,
                                            size=20,
                                            weight=ft.FontWeight.W_700,
                                            color=color,
                                        ),
                                    ],
                                    spacing=2,
                                    expand=True,
                                ),
                            ],
                            spacing=12,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=14,
                        **card_style(),
                    )
                )
            page.show_dialog(
                ft.AlertDialog(
                    title=ft.Text("Обзор недели", color=TEXT),
                    content=ft.Column(
                        [
                            muted(f"Неделя {period}"),
                            *rows,
                        ],
                        spacing=10,
                        tight=True,
                        scroll=ft.ScrollMode.AUTO,
                        height=340,
                        width=300,
                    ),
                    actions=[
                        ft.TextButton("Закрыть", on_click=lambda e: page.pop_dialog()),
                    ],
                )
            )

        week_pct = 0.0 if week_target <= 0 else min(1.0, week_done / week_target)
        week_goal_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(
                                f"Неделя: {week_done}/{week_target} задач",
                                size=13,
                                weight=ft.FontWeight.W_700,
                                color=TEXT,
                                expand=True,
                            ),
                            ft.Text(
                                f"{int(round(week_pct * 100))}%",
                                size=12,
                                weight=ft.FontWeight.W_600,
                                color=ORANGE if week_pct >= 1.0 else MUTED,
                            ),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.ProgressBar(
                        value=week_pct,
                        color=ORANGE,
                        bgcolor="#2A2A32",
                        bar_height=8,
                    ),
                ],
                spacing=8,
            ),
            padding=14,
            bgcolor="#1A1A22",
            border=ft.Border.all(1, ORANGE if week_pct >= 1.0 else BORDER),
            border_radius=ft.BorderRadius.all(14),
            tooltip="Цель недели · ISO пн–вс · completed_at",
        )

        root_col.controls.extend(
            [
                ft.Row(
                    [
                        ft.Text(
                            "Аналитика",
                            size=26,
                            weight=ft.FontWeight.W_700,
                            color=TEXT,
                            expand=True,
                        ),
                        ft.Container(
                            content=ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, color=ORANGE, size=18),
                            width=36,
                            height=36,
                            bgcolor="#1C1C22",
                            border=ft.Border.all(1, BORDER),
                            border_radius=ft.BorderRadius.all(10),
                            alignment=ft.Alignment.CENTER,
                            on_click=lambda e: on_open_note("analytics.md", "Аналитика") if on_open_note else None,
                            ink=True,
                            tooltip="Заметка · analytics.md",
                        ),
                        ft.Container(
                            content=ft.Text(
                                "Обзор недели",
                                size=12,
                                weight=ft.FontWeight.W_700,
                                color="#0F0F12",
                            ),
                            bgcolor=ORANGE,
                            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                            border_radius=ft.BorderRadius.all(10),
                            on_click=show_weekly_review,
                            ink=True,
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                muted("Статусы, фокус, серии и активность"),
                week_goal_card,
                review_section,
                ft.Container(
                    content=ft.Row(
                        [
                            pie,
                            ft.Column(
                                [
                                    _row("К выполнению", dist.todo, MUTED),
                                    _row("В работе", dist.in_progress, ORANGE),
                                    _row("Готово", dist.done, GREEN),
                                    ft.Text(
                                        f"Завершение {stats.completion_rate}%",
                                        size=13,
                                        color=ORANGE,
                                        weight=ft.FontWeight.W_600,
                                    ),
                                ],
                                spacing=8,
                                expand=True,
                            ),
                        ],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=16,
                    **card_style(),
                ),
                streak_section,
                focus_section,
                focus_notes_section,
                heat_section,
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                "Активность · 14 дней",
                                size=14,
                                weight=ft.FontWeight.W_600,
                                color=TEXT,
                            ),
                            line,
                        ],
                        spacing=10,
                    ),
                    padding=16,
                    **card_style(),
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                "Прогресс целей",
                                size=14,
                                weight=ft.FontWeight.W_600,
                                color=TEXT,
                            ),
                            goal_rings if goals else empty_illus("Нет целей", emoji="🎯"),
                        ],
                        spacing=12,
                    ),
                    padding=16,
                    **card_style(),
                ),
                forecast_section,
                ft.Container(height=8),
            ]
        )
        page.update()

    def _row(label: str, value: int, color: str) -> ft.Control:
        return ft.Row(
            [
                ft.Container(width=8, height=8, bgcolor=color, border_radius=4),
                ft.Text(label, size=12, color=MUTED, expand=True),
                ft.Text(str(value), size=13, weight=ft.FontWeight.W_600, color=TEXT),
            ],
            spacing=8,
        )

    reload()
    return ft.Container(
        content=root_col,
        padding=ft.Padding.only(left=16, right=16, top=18, bottom=8),
        expand=True,
    )
