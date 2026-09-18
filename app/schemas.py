"""Pydantic v2 schemas for validation / transfer."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional, TypedDict

from pydantic import BaseModel, Field, field_validator


TaskStatus = Literal["todo", "in_progress", "done"]
TaskPriority = Literal["low", "medium", "high"]
RecurRule = Literal["none", "daily", "weekly"]
NodeStatus = Literal["pending", "active", "done"]
SessionStatus = Literal["running", "paused", "done"]


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    status: TaskStatus = "todo"
    priority: TaskPriority = "medium"
    due_date: Optional[date] = None
    goal_id: Optional[int] = None
    color_tag: Optional[str] = None
    pinned: bool = False
    archived: bool = False
    recur_rule: RecurRule = "none"
    recur_anchor: Optional[date] = None
    estimated_min: Optional[int] = Field(default=None, ge=0, le=24 * 60)
    inbox: bool = False

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title required")
        return v


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[date] = None
    goal_id: Optional[int] = None
    color_tag: Optional[str] = None
    pinned: Optional[bool] = None
    archived: Optional[bool] = None
    recur_rule: Optional[RecurRule] = None
    recur_anchor: Optional[date] = None
    estimated_min: Optional[int] = Field(default=None, ge=0, le=24 * 60)
    inbox: Optional[bool] = None


class TaskOut(BaseModel):
    id: int
    title: str
    description: str
    status: TaskStatus
    priority: TaskPriority
    due_date: Optional[date]
    goal_id: Optional[int]
    color_tag: Optional[str] = None
    pinned: bool = False
    archived: bool = False
    recur_rule: RecurRule = "none"
    recur_anchor: Optional[date] = None
    estimated_min: Optional[int] = None
    inbox: bool = False
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SubtaskCreate(BaseModel):
    task_id: int
    title: str = Field(min_length=1, max_length=200)
    done: bool = False
    position: Optional[int] = None

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title required")
        return v


class SubtaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    done: Optional[bool] = None
    position: Optional[int] = None


class SubtaskOut(BaseModel):
    id: int
    task_id: int
    title: str
    done: bool
    position: int

    model_config = {"from_attributes": True}


class GoalCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    target_value: float = Field(gt=0)
    unit: str = "units"
    daily_quota: float = Field(gt=0)

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title required")
        return v


class GoalUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    target_value: Optional[float] = Field(default=None, gt=0)
    unit: Optional[str] = None
    daily_quota: Optional[float] = Field(default=None, gt=0)
    current_value: Optional[float] = Field(default=None, ge=0)
    archived: Optional[bool] = None


class ProgressLogCreate(BaseModel):
    goal_id: int
    amount: float = Field(gt=0)
    note: str = ""


class ProgressLogUpdate(BaseModel):
    amount: Optional[float] = Field(default=None, gt=0)
    note: Optional[str] = None


class ProgressLogOut(BaseModel):
    id: int
    goal_id: int
    amount: float
    note: str
    logged_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class GoalOut(BaseModel):
    id: int
    title: str
    description: str
    target_value: float
    unit: str
    daily_quota: float
    current_value: float
    percent_complete: float
    archived: bool = False

    model_config = {"from_attributes": True}


class StatusDistribution(BaseModel):
    todo: int = 0
    in_progress: int = 0
    done: int = 0


class DailyPoint(BaseModel):
    day: date
    completed: int


class GoalForecast(BaseModel):
    goal_id: int
    title: str
    days_to_complete: Optional[int] = None
    percent_complete: float = 0.0
    daily_quota: float = 0.0
    unit: str = "units"
    remaining: float = 0.0


class WeeklyFocusStats(BaseModel):
    sessions_count: int = 0
    total_sec: int = 0
    total_min: int = 0
    days: list[DailyPoint] = []


class FocusNoteSnippet(BaseModel):
    """Recent completed focus session with a note — Analytics list."""

    session_id: int
    title: str
    note_snippet: str


class OverviewStats(BaseModel):
    total_tasks: int = 0
    done_tasks: int = 0
    active_tasks: int = 0
    goals: int = 0
    overdue_tasks: int = 0
    completion_rate: float = 0.0


class WeekDueSummary(TypedDict):
    start: date
    end: date
    tasks: list  # list[Task] — ORM rows
    count: int
    overdue: int
    due_today: int


class SearchResult(TypedDict):
    tasks: list  # list[Task]
    goals: list  # list[Goal]
    query: str


class HeatmapDay(BaseModel):
    day: date
    count: int


class StreakInfo(BaseModel):
    goal_id: int
    title: str
    current_streak: int
    best_streak: int
    today_complete: bool


class SettingsOut(BaseModel):
    display_name: str = "Рома"
    accent_hex: str = "#FF8A00"
    week_starts_monday: bool = True
    pomodoro_work_min: int = Field(default=25, ge=5, le=90)
    pomodoro_break_min: int = Field(default=5, ge=1, le=30)
    archive_on_recur_done: bool = False
    quiet_start: int = Field(default=22, ge=0, le=23)
    quiet_end: int = Field(default=8, ge=0, le=23)
    auto_complete_subtasks: bool = False
    compact_ui: bool = False
    haptics_enabled: bool = True
    wind_down_hour: int = Field(default=18, ge=0, le=23)
    weekly_task_target: int = Field(default=10, ge=1, le=200)


class SettingsUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    accent_hex: Optional[str] = Field(default=None, min_length=4, max_length=7)
    week_starts_monday: Optional[bool] = None
    pomodoro_work_min: Optional[int] = Field(default=None, ge=5, le=90)
    pomodoro_break_min: Optional[int] = Field(default=None, ge=1, le=30)
    archive_on_recur_done: Optional[bool] = None
    quiet_start: Optional[int] = Field(default=None, ge=0, le=23)
    quiet_end: Optional[int] = Field(default=None, ge=0, le=23)
    auto_complete_subtasks: Optional[bool] = None
    compact_ui: Optional[bool] = None
    haptics_enabled: Optional[bool] = None
    wind_down_hour: Optional[int] = Field(default=None, ge=0, le=23)
    weekly_task_target: Optional[int] = Field(default=None, ge=1, le=200)

    @field_validator("accent_hex")
    @classmethod
    def validate_hex(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v.startswith("#"):
            v = "#" + v
        if len(v) not in (4, 7):
            raise ValueError("accent_hex must be #RGB or #RRGGBB")
        for ch in v[1:]:
            if ch.lower() not in "0123456789abcdef":
                raise ValueError("invalid hex color")
        return v.upper() if len(v) == 7 else v


class RoadmapNodeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    x: float = 40.0
    y: float = 40.0
    status: NodeStatus = "pending"
    task_id: Optional[int] = None


class RoadmapNodeUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    x: Optional[float] = None
    y: Optional[float] = None
    status: Optional[NodeStatus] = None
    task_id: Optional[int] = None


class RoadmapEdgeCreate(BaseModel):
    from_node_id: int
    to_node_id: int


class TimeSessionCreate(BaseModel):
    task_id: Optional[int] = None
    label: str = "Фокус"
    duration_sec: int = Field(default=25 * 60, gt=0)
    note: str = ""


class TimeSessionUpdate(BaseModel):
    task_id: Optional[int] = None
    label: Optional[str] = None
    duration_sec: Optional[int] = Field(default=None, gt=0)
    remaining_sec: Optional[int] = Field(default=None, ge=0)
    status: Optional[SessionStatus] = None
    note: Optional[str] = None


class WeeklyReview(BaseModel):
    """Calendar-week rollup for Analytics «Обзор недели»."""

    week_start: date
    week_end: date
    completed_count: int = 0
    focus_min: int = 0
    quotas_met_days: int = 0
    best_streak: int = 0


class MomentumScore(BaseModel):
    """0–100 home momentum: quotas + completion + capped best streak."""

    score: int = 0
    quotas_pct: float = 0.0
    completion_pct: float = 0.0
    streak_pct: float = 0.0
    best_streak: int = 0
    streak_cap: int = 14


class StuckGoal(BaseModel):
    """Active incomplete goal with no ProgressLog for ``days_idle``+ days."""

    goal_id: int
    title: str
    days_idle: int
    percent_complete: float = 0.0
    last_logged_at: Optional[datetime] = None


class DailyWrap(BaseModel):
    """Home «Итог дня» snapshot for today."""

    day: date
    quotas_met: int = 0
    quotas_total: int = 0
    tasks_done: int = 0
    focus_min: int = 0
    tip_tomorrow: str = ""


class SmartSuggestion(BaseModel):
    """Home contextual one-liner, dismissible for today."""

    kind: Literal["stuck", "overdue", "quota"]
    text: str
    goal_id: Optional[int] = None


class IncompleteQuota(BaseModel):
    """Open daily quota row for morning briefing."""

    goal_id: int
    title: str
    today: float = 0.0
    quota: float = 0.0


class MorningBriefing(BaseModel):
    """Home «Брифинг» start-of-day snapshot."""

    day: date
    overdue_count: int = 0
    due_today: int = 0
    incomplete_quotas: list[IncompleteQuota] = []
    momentum: MomentumScore = Field(default_factory=MomentumScore)
    suggestion: Optional[SmartSuggestion] = None


class TomorrowPlanItem(BaseModel):
    """One task row in «План на завтра»."""

    task_id: int
    title: str
    priority: str = "medium"
    estimated_min: Optional[int] = None


class TomorrowPlan(BaseModel):
    """Home «Завтра» preview: due tomorrow + open today (carry hint)."""

    day: date  # tomorrow's date
    due_tomorrow: list[TomorrowPlanItem] = []
    open_today: list[TomorrowPlanItem] = []
    tip: str = ""



# --- Vault / Markdown notes ---

class NoteWrite(BaseModel):
    """Validate note filename + content before disk write."""

    filename: str = Field(min_length=1, max_length=128)
    content: str = ""

    @field_validator("filename")
    @classmethod
    def safe_name(cls, v: str) -> str:
        from app.services.notes_service import sanitize_filename

        return sanitize_filename(v)


class NoteCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=128)
    content: str = ""

    @field_validator("filename")
    @classmethod
    def safe_name(cls, v: str) -> str:
        from app.services.notes_service import sanitize_filename

        return sanitize_filename(v)


class NoteOut(BaseModel):
    filename: str
    content: str
    title: str = ""


# --- Infinite canvas ---

CanvasKind = Literal["section", "note", "roadmap"]


class CanvasNodeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    x: float = 0.0
    y: float = 0.0
    kind: CanvasKind = "note"
    ref: str = ""
    color: Optional[str] = None
    w: float = Field(default=160.0, ge=80.0, le=480.0)
    h: float = Field(default=72.0, ge=48.0, le=320.0)

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title required")
        return v

    @field_validator("ref")
    @classmethod
    def clean_ref(cls, v: str) -> str:
        """Strip path segments from MD refs; keep roadmap ids intact."""
        raw = (v or "").strip()
        if not raw:
            return ""
        base = raw.replace("\\", "/").split("/")[-1]
        if base.endswith(".md") or raw.endswith(".md"):
            from app.services.notes_service import sanitize_filename

            return sanitize_filename(base)
        return base[:255]


class CanvasNodeUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    x: Optional[float] = None
    y: Optional[float] = None
    kind: Optional[CanvasKind] = None
    ref: Optional[str] = None
    color: Optional[str] = None
    w: Optional[float] = Field(default=None, ge=80.0, le=480.0)
    h: Optional[float] = Field(default=None, ge=48.0, le=320.0)

    @field_validator("ref")
    @classmethod
    def clean_ref_upd(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return CanvasNodeCreate.clean_ref(v)


class CanvasNodeOut(BaseModel):
    id: int
    title: str
    x: float
    y: float
    kind: CanvasKind
    ref: str
    color: Optional[str] = None
    w: float
    h: float

    model_config = {"from_attributes": True}


class CanvasEdgeCreate(BaseModel):
    from_node_id: int
    to_node_id: int


class CanvasEdgeOut(BaseModel):
    id: int
    from_node_id: int
    to_node_id: int

    model_config = {"from_attributes": True}
