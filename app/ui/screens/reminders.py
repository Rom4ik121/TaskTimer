"""In-app reminder center — due today, overdue, incomplete goal quotas."""
from __future__ import annotations

import flet as ft

from app.db import get_session
from app.services import reminder_service
from app.ui.components.cards import empty_state
from app.ui.theme import MUTED, ORANGE, RED, TEXT, card_style, muted, section_title


def build_reminders(
    page: ft.Page,
    *,
    on_back,
    on_open_task=None,
    on_open_goal=None,
    on_open_overdue=None,
) -> ft.Control:
    body = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)

    def reload(_: ft.ControlEvent | None = None):
        body.controls.clear()
        with get_session() as session:
            data = reminder_service.list_reminders(session)

        due_today = data["due_today"]
        overdue = data["overdue"]
        incomplete = data["incomplete_goals"]
        total = data["count"]

        header = ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK_IOS_NEW,
                    icon_color=TEXT,
                    icon_size=18,
                    on_click=lambda e: on_back(),
                ),
                ft.Column(
                    [
                        ft.Text(
                            "Напоминания",
                            size=22,
                            weight=ft.FontWeight.W_700,
                            color=TEXT,
                        ),
                        muted(f"{total} пунктов · сегодня"),
                    ],
                    spacing=2,
                    expand=True,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        body.controls.append(header)

        if total == 0:
            body.controls.append(
                empty_state("Всё спокойно", "Нет сроков на сегодня и просрочек", emoji="🌿")
            )
            page.update()
            return

        # Overdue
        if overdue:
            body.controls.append(section_title(f"Просрочено · {len(overdue)}"))
            rows = []
            for t in overdue:
                rows.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.EVENT_BUSY, color=RED, size=18),
                                ft.Column(
                                    [
                                        ft.Text(
                                            t.title,
                                            size=14,
                                            weight=ft.FontWeight.W_600,
                                            color=TEXT,
                                            max_lines=1,
                                            overflow=ft.TextOverflow.ELLIPSIS,
                                        ),
                                        ft.Text(
                                            f"срок {t.due_date.isoformat()}" if t.due_date else "",
                                            size=11,
                                            color=RED,
                                        ),
                                    ],
                                    spacing=2,
                                    expand=True,
                                ),
                            ],
                            spacing=10,
                        ),
                        padding=12,
                        **card_style(),
                        on_click=(lambda e, tid=t.id: on_open_task(tid) if on_open_task else None),
                        ink=True,
                    )
                )
            body.controls.extend(rows)
            if on_open_overdue:
                body.controls.append(
                    ft.TextButton(
                        "Все просроченные в Задачах →",
                        on_click=lambda e: on_open_overdue(),
                        style=ft.ButtonStyle(color=RED),
                    )
                )

        # Due today
        if due_today:
            body.controls.append(section_title(f"Срок сегодня · {len(due_today)}"))
            for t in due_today:
                body.controls.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.TODAY, color=ORANGE, size=18),
                                ft.Text(
                                    t.title,
                                    size=14,
                                    weight=ft.FontWeight.W_600,
                                    color=TEXT,
                                    expand=True,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                            ],
                            spacing=10,
                        ),
                        padding=12,
                        **card_style(),
                        on_click=(lambda e, tid=t.id: on_open_task(tid) if on_open_task else None),
                        ink=True,
                    )
                )

        # Incomplete goals
        if incomplete:
            body.controls.append(section_title(f"Квоты не закрыты · {len(incomplete)}"))
            for q in incomplete:
                g = q["goal"]
                body.controls.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.FLAG_OUTLINED, color=ORANGE, size=18),
                                ft.Column(
                                    [
                                        ft.Text(
                                            g.title,
                                            size=14,
                                            weight=ft.FontWeight.W_600,
                                            color=TEXT,
                                            max_lines=1,
                                            overflow=ft.TextOverflow.ELLIPSIS,
                                        ),
                                        ft.Text(
                                            f"{q['today']:g} / {q['quota']:g} {g.unit}",
                                            size=11,
                                            color=MUTED,
                                        ),
                                    ],
                                    spacing=2,
                                    expand=True,
                                ),
                            ],
                            spacing=10,
                        ),
                        padding=12,
                        **card_style(),
                        on_click=(
                            lambda e, gid=g.id: on_open_goal(gid) if on_open_goal else None
                        ),
                        ink=True,
                    )
                )

        body.controls.append(ft.Container(height=8))
        page.update()

    reload()
    return ft.Container(
        content=body,
        padding=ft.Padding.only(left=16, right=16, top=18, bottom=8),
        expand=True,
    )
