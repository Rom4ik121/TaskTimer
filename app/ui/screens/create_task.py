"""Create task & goal form — task/goal templates, goal link, date picker, Russian labels."""
from __future__ import annotations

import flet as ft
from pydantic import ValidationError

from app.db import get_session
from app.schemas import GoalCreate, TaskCreate
from app.services import goal_service, task_service
from app.ui.components.dialogs import pick_date, show_snack
from app.ui.theme import BORDER, MUTED, ORANGE, TEXT, card_style, muted

# Prefill chips for task mode (priority / recur)
TASK_TEMPLATES: list[tuple[str, dict]] = [
    ("Срочное", {"priority": "high", "recur_rule": "none"}),
    ("Обычное", {"priority": "medium", "recur_rule": "none"}),
    ("Повтор daily", {"priority": "medium", "recur_rule": "daily"}),
]

# Prefill chips for goal mode
GOAL_TEMPLATES: list[tuple[str, dict | None]] = [
    (
        "Книга 10 стр/день",
        {
            "title": "Чтение",
            "description": "Читать по 10 страниц в день",
            "target": "300",
            "unit": "стр",
            "quota": "10",
        },
    ),
    (
        "Спорт",
        {
            "title": "Спорт",
            "description": "Регулярные тренировки",
            "target": "30",
            "unit": "тренировок",
            "quota": "1",
        },
    ),
    (
        "Учёба 1.5ч",
        {
            "title": "Учёба",
            "description": "Учёба 1.5 часа в день",
            "target": "100",
            "unit": "часов",
            "quota": "1.5",
        },
    ),
    ("Кастом", None),
]


def build_create_task(page: ft.Page, *, on_done, refresh_all) -> ft.Control:
    mode = {"value": "task"}
    due_state = {"value": None}
    active_goal_tpl = {"value": None}
    active_task_tpl = {"value": None}

    with get_session() as session:
        goals = goal_service.list_goals(session)

    title = ft.TextField(
        label="Название",
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
        cursor_color=ORANGE,
    )
    description = ft.TextField(
        label="Описание / заметки",
        multiline=True,
        min_lines=2,
        max_lines=8,
        hint_text="Поддерживается **жирный**",
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
    )
    status_dd = ft.Dropdown(
        label="Статус",
        value="todo",
        options=[
            ft.dropdown.Option("todo", "К выполнению"),
            ft.dropdown.Option("in_progress", "В работе"),
            ft.dropdown.Option("done", "Готово"),
        ],
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
    )
    priority_dd = ft.Dropdown(
        label="Приоритет",
        value="medium",
        options=[
            ft.dropdown.Option("low", "Низкий"),
            ft.dropdown.Option("medium", "Средний"),
            ft.dropdown.Option("high", "Высокий"),
        ],
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
    )
    goal_dd = ft.Dropdown(
        label="Цель",
        value="",
        options=[ft.dropdown.Option("", "Без цели")]
        + [ft.dropdown.Option(str(g.id), g.title) for g in goals],
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
    )
    color_dd = ft.Dropdown(
        label="Метка",
        value="нет",
        options=[
            ft.dropdown.Option("нет", "Нет"),
            ft.dropdown.Option("оранжевый", "Оранжевый"),
            ft.dropdown.Option("синий", "Синий"),
            ft.dropdown.Option("зелёный", "Зелёный"),
            ft.dropdown.Option("красный", "Красный"),
            ft.dropdown.Option("фиолетовый", "Фиолетовый"),
        ],
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
    )
    due_label = ft.Text("Не выбран", size=14, color=TEXT)

    recur_dd = ft.Dropdown(
        label="Повтор",
        value="none",
        options=[
            ft.dropdown.Option("none", "Нет"),
            ft.dropdown.Option("daily", "Ежедневно"),
            ft.dropdown.Option("weekly", "Еженедельно"),
        ],
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
    )
    estimate_field = ft.TextField(
        label="Оценка, мин",
        value="",
        keyboard_type=ft.KeyboardType.NUMBER,
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
        hint_text="например 25",
    )

    target = ft.TextField(
        label="Цель (число)",
        value="100",
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
        visible=False,
    )
    unit = ft.TextField(
        label="Единица",
        value="страниц",
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
        visible=False,
    )
    quota = ft.TextField(
        label="Дневная квота",
        value="10",
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
        visible=False,
    )

    err = ft.Text("", color="#FF5C5C", size=12)
    due_row = ft.Row(
        [
            ft.Column([muted("Срок"), due_label], spacing=2, expand=True),
            ft.TextButton(
                "Календарь",
                on_click=lambda e: pick_date(
                    page,
                    value=due_state["value"],
                    on_picked=lambda d: (
                        due_state.update(value=d),
                        setattr(due_label, "value", d.isoformat() if d else "Не выбран"),
                        page.update(),
                    ),
                ),
            ),
            ft.TextButton(
                "Сбросить",
                on_click=lambda e: (
                    due_state.update(value=None),
                    setattr(due_label, "value", "Не выбран"),
                    page.update(),
                ),
            ),
        ],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    goal_tpl_chips: list[ft.Container] = []
    task_tpl_chips: list[ft.Container] = []

    def _chip_text_color(chip: ft.Container, color: str) -> None:
        content = getattr(chip, "content", None)
        if content is not None and hasattr(content, "color"):
            content.color = color

    def _paint_goal_tpl_chips():
        for i, chip in enumerate(goal_tpl_chips):
            label = GOAL_TEMPLATES[i][0]
            active = active_goal_tpl["value"] == label
            chip.bgcolor = ORANGE if active else "transparent"
            chip.border = ft.Border.all(1, ORANGE if active else BORDER)
            _chip_text_color(chip, "#0F0F12" if active else MUTED)

    def _paint_task_tpl_chips():
        for i, chip in enumerate(task_tpl_chips):
            label = TASK_TEMPLATES[i][0]
            active = active_task_tpl["value"] == label
            chip.bgcolor = ORANGE if active else "transparent"
            chip.border = ft.Border.all(1, ORANGE if active else BORDER)
            _chip_text_color(chip, "#0F0F12" if active else MUTED)

    # Placeholder rows/tabs — filled below; set_mode closes over these names.
    goal_templates_row = ft.Column(spacing=6, visible=False)
    task_templates_row = ft.Column(spacing=6, visible=True)
    task_tab = ft.Container()
    goal_tab = ft.Container()

    def set_mode(m: str, *, update: bool = True):
        """Switch task/goal form; keep goal fields + goal templates visible in goal mode."""
        mode["value"] = m
        is_goal = m == "goal"
        status_dd.visible = not is_goal
        priority_dd.visible = not is_goal
        goal_dd.visible = not is_goal
        color_dd.visible = not is_goal
        recur_dd.visible = not is_goal
        estimate_field.visible = not is_goal
        due_row.visible = not is_goal
        # Goal-only fields must stay visible in goal mode (templates must not hide them)
        target.visible = is_goal
        unit.visible = is_goal
        quota.visible = is_goal
        goal_templates_row.visible = is_goal
        task_templates_row.visible = not is_goal
        if is_goal:
            active_task_tpl["value"] = None
            _paint_task_tpl_chips()
        else:
            active_goal_tpl["value"] = None
            _paint_goal_tpl_chips()
        if task_tab.content is not None:
            task_tab.bgcolor = ORANGE if not is_goal else "transparent"
            task_tab.border = None if not is_goal else ft.Border.all(1, BORDER)
            _chip_text_color(task_tab, "#0F0F12" if not is_goal else MUTED)
        if goal_tab.content is not None:
            goal_tab.bgcolor = ORANGE if is_goal else "transparent"
            goal_tab.border = None if is_goal else ft.Border.all(1, BORDER)
            _chip_text_color(goal_tab, "#0F0F12" if is_goal else MUTED)
        if update:
            page.update()

    def apply_goal_template(label: str, data: dict | None):
        set_mode("goal", update=False)
        active_goal_tpl["value"] = label
        if data is None:
            title.value = ""
            description.value = ""
            target.value = "100"
            unit.value = "ед"
            quota.value = "1"
        else:
            title.value = data["title"]
            description.value = data.get("description", "")
            target.value = data["target"]
            unit.value = data["unit"]
            quota.value = data["quota"]
        # Re-assert goal visibility after template fill (Wave P task chips must not leak)
        target.visible = True
        unit.visible = True
        quota.visible = True
        goal_templates_row.visible = True
        task_templates_row.visible = False
        _paint_goal_tpl_chips()
        page.update()

    def apply_task_template(label: str, data: dict):
        set_mode("task", update=False)
        active_task_tpl["value"] = label
        priority_dd.value = data.get("priority", "medium")
        recur_dd.value = data.get("recur_rule", "none")
        target.visible = False
        unit.visible = False
        quota.visible = False
        goal_templates_row.visible = False
        task_templates_row.visible = True
        _paint_task_tpl_chips()
        page.update()

    for label, data in GOAL_TEMPLATES:
        chip = ft.Container(
            content=ft.Text(label, size=11, color=MUTED, weight=ft.FontWeight.W_500),
            padding=ft.Padding.symmetric(horizontal=10, vertical=7),
            border_radius=ft.BorderRadius.all(16),
            border=ft.Border.all(1, BORDER),
            on_click=lambda e, lb=label, d=data: apply_goal_template(lb, d),
        )
        goal_tpl_chips.append(chip)

    for label, data in TASK_TEMPLATES:
        chip = ft.Container(
            content=ft.Text(label, size=11, color=MUTED, weight=ft.FontWeight.W_500),
            padding=ft.Padding.symmetric(horizontal=10, vertical=7),
            border_radius=ft.BorderRadius.all(16),
            border=ft.Border.all(1, BORDER),
            on_click=lambda e, lb=label, d=data: apply_task_template(lb, d),
        )
        task_tpl_chips.append(chip)

    goal_templates_row.controls = [
        muted("Шаблоны цели"),
        ft.Row(goal_tpl_chips, spacing=8, scroll=ft.ScrollMode.AUTO),
    ]
    task_templates_row.controls = [
        muted("Шаблоны задачи"),
        ft.Row(task_tpl_chips, spacing=8, scroll=ft.ScrollMode.AUTO),
    ]

    task_tab.content = ft.Text("Задача", size=13, weight=ft.FontWeight.W_600, color="#0F0F12")
    task_tab.bgcolor = ORANGE
    task_tab.padding = ft.Padding.symmetric(horizontal=18, vertical=10)
    task_tab.border_radius = ft.BorderRadius.all(20)
    task_tab.on_click = lambda e: set_mode("task")

    goal_tab.content = ft.Text("Цель", size=13, weight=ft.FontWeight.W_600, color=MUTED)
    goal_tab.padding = ft.Padding.symmetric(horizontal=18, vertical=10)
    goal_tab.border_radius = ft.BorderRadius.all(20)
    goal_tab.border = ft.Border.all(1, BORDER)
    goal_tab.on_click = lambda e: set_mode("goal")

    def save(_):
        err.value = ""
        try:
            if mode["value"] == "task":
                gid = goal_dd.value
                tag = color_dd.value
                em_raw = (estimate_field.value or "").strip()
                em_val = int(em_raw) if em_raw else None
                data = TaskCreate(
                    title=title.value or "",
                    description=description.value or "",
                    status=status_dd.value or "todo",  # type: ignore[arg-type]
                    priority=priority_dd.value or "medium",  # type: ignore[arg-type]
                    due_date=due_state["value"],
                    goal_id=int(gid) if gid else None,
                    color_tag=None if not tag or tag == "нет" else tag,
                    recur_rule=recur_dd.value or "none",  # type: ignore[arg-type]
                    recur_anchor=due_state["value"],
                    estimated_min=em_val,
                )
                with get_session() as session:
                    task_service.create_task(session, data)
            else:
                data = GoalCreate(
                    title=title.value or "",
                    description=description.value or "",
                    target_value=float((target.value or "0").replace(",", ".")),
                    unit=unit.value or "units",
                    daily_quota=float((quota.value or "1").replace(",", ".")),
                )
                with get_session() as session:
                    goal_service.create_goal(session, data)
        except (ValidationError, ValueError) as exc:
            err.value = str(exc)
            page.update()
            return
        show_snack(page, "Сохранено")
        refresh_all()
        on_done()

    return ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.IconButton(
                            icon=ft.Icons.ARROW_BACK_IOS_NEW,
                            icon_color=TEXT,
                            icon_size=18,
                            on_click=lambda e: on_done(),
                        ),
                        ft.Text("Создать", size=22, weight=ft.FontWeight.W_700, color=TEXT),
                    ]
                ),
                ft.Row([task_tab, goal_tab], spacing=10),
                task_templates_row,
                goal_templates_row,
                ft.Container(
                    content=ft.Column(
                        [
                            title,
                            description,
                            status_dd,
                            priority_dd,
                            goal_dd,
                            color_dd,
                            recur_dd,
                            estimate_field,
                            due_row,
                            target,
                            unit,
                            quota,
                            err,
                        ],
                        spacing=12,
                    ),
                    padding=16,
                    **card_style(),
                ),
                ft.Container(
                    content=ft.Text(
                        "Сохранить", size=15, weight=ft.FontWeight.W_700, color="#0F0F12"
                    ),
                    bgcolor=ORANGE,
                    padding=16,
                    border_radius=ft.BorderRadius.all(14),
                    alignment=ft.Alignment.CENTER,
                    on_click=save,
                    ink=True,
                ),
                muted("Форма проверяется через Pydantic перед записью"),
            ],
            spacing=14,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        ),
        padding=ft.Padding.only(left=16, right=16, top=18, bottom=8),
        expand=True,
    )
