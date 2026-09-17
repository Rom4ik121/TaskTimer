"""Analytics aggregations — uses completed_at honestly."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Goal, ProgressLog, Task, TimeSession
from app.schemas import (
    DailyPoint,
    DailyWrap,
    FocusNoteSnippet,
    GoalForecast,
    HeatmapDay,
    IncompleteQuota,
    MomentumScore,
    MorningBriefing,
    OverviewStats,
    SmartSuggestion,
    StatusDistribution,
    StuckGoal,
    TomorrowPlan,
    TomorrowPlanItem,
    WeeklyFocusStats,
    WeeklyReview,
)


def status_distribution(session: Session) -> StatusDistribution:
    rows = session.execute(
        select(Task.status, func.count(Task.id))
        .where(Task.archived.is_(False))
        .group_by(Task.status)
    ).all()
    data = {status: count for status, count in rows}
    return StatusDistribution(
        todo=data.get("todo", 0),
        in_progress=data.get("in_progress", 0),
        done=data.get("done", 0),
    )


def completed_last_n_days(session: Session, days: int = 14) -> list[DailyPoint]:
    today = date.today()
    start = today - timedelta(days=days - 1)
    start_dt = datetime.combine(start, datetime.min.time())

    # Honest completion count via completed_at (not updated_at)
    rows = session.execute(
        select(func.date(Task.completed_at), func.count(Task.id))
        .where(Task.status == "done")
        .where(Task.archived.is_(False))
        .where(Task.completed_at.is_not(None))
        .where(Task.completed_at >= start_dt)
        .group_by(func.date(Task.completed_at))
    ).all()
    by_day: dict[date, int] = {}
    for day_val, count in rows:
        if isinstance(day_val, str):
            d = date.fromisoformat(day_val)
        elif isinstance(day_val, date):
            d = day_val
        else:
            continue
        by_day[d] = int(count)

    # Progress logs as secondary activity signal
    log_rows = session.execute(
        select(func.date(ProgressLog.logged_at), func.count(ProgressLog.id))
        .where(ProgressLog.logged_at >= start_dt)
        .group_by(func.date(ProgressLog.logged_at))
    ).all()
    for day_val, count in log_rows:
        if isinstance(day_val, str):
            d = date.fromisoformat(day_val)
        elif isinstance(day_val, date):
            d = day_val
        else:
            continue
        by_day[d] = by_day.get(d, 0) + int(count)

    points: list[DailyPoint] = []
    for i in range(days):
        d = start + timedelta(days=i)
        points.append(DailyPoint(day=d, completed=by_day.get(d, 0)))
    return points


def activity_heatmap(session: Session, weeks: int = 14) -> list[HeatmapDay]:
    """Daily activity counts for last N weeks (logs + task completions)."""
    weeks = max(12, min(16, weeks))
    days = weeks * 7
    today = date.today()
    start = today - timedelta(days=days - 1)
    start_dt = datetime.combine(start, datetime.min.time())

    by_day: dict[date, int] = {}

    rows = session.execute(
        select(func.date(Task.completed_at), func.count(Task.id))
        .where(Task.status == "done")
        .where(Task.archived.is_(False))
        .where(Task.completed_at.is_not(None))
        .where(Task.completed_at >= start_dt)
        .group_by(func.date(Task.completed_at))
    ).all()
    for day_val, count in rows:
        if isinstance(day_val, str):
            d = date.fromisoformat(day_val)
        elif isinstance(day_val, date):
            d = day_val
        else:
            continue
        by_day[d] = by_day.get(d, 0) + int(count)

    log_rows = session.execute(
        select(func.date(ProgressLog.logged_at), func.count(ProgressLog.id))
        .where(ProgressLog.logged_at >= start_dt)
        .group_by(func.date(ProgressLog.logged_at))
    ).all()
    for day_val, count in log_rows:
        if isinstance(day_val, str):
            d = date.fromisoformat(day_val)
        elif isinstance(day_val, date):
            d = day_val
        else:
            continue
        by_day[d] = by_day.get(d, 0) + int(count)

    out: list[HeatmapDay] = []
    for i in range(days):
        d = start + timedelta(days=i)
        out.append(HeatmapDay(day=d, count=by_day.get(d, 0)))
    return out


def overview_stats(session: Session) -> OverviewStats:
    total = (
        session.scalar(select(func.count(Task.id)).where(Task.archived.is_(False))) or 0
    )
    done = (
        session.scalar(
            select(func.count(Task.id))
            .where(Task.status == "done")
            .where(Task.archived.is_(False))
        )
        or 0
    )
    active = (
        session.scalar(
            select(func.count(Task.id))
            .where(Task.status.in_(["todo", "in_progress"]))
            .where(Task.archived.is_(False))
        )
        or 0
    )
    goals = (
        session.scalar(
            select(func.count(Goal.id)).where(Goal.archived.is_(False))
        )
        or 0
    )
    overdue = (
        session.scalar(
            select(func.count(Task.id))
            .where(Task.status != "done")
            .where(Task.archived.is_(False))
            .where(Task.due_date.is_not(None))
            .where(Task.due_date < date.today())
        )
        or 0
    )
    rate = round(100.0 * done / total, 1) if total else 0.0
    return OverviewStats(
        total_tasks=total,
        done_tasks=done,
        active_tasks=active,
        goals=goals,
        overdue_tasks=overdue,
        completion_rate=rate,
    )


def weekly_focus_stats(session: Session, days: int = 7) -> WeeklyFocusStats:
    """Sum completed TimeSession duration over the last N days + per-day tiles."""
    days = max(1, min(31, days))
    today = date.today()
    start = today - timedelta(days=days - 1)
    start_dt = datetime.combine(start, datetime.min.time())

    sessions = list(
        session.scalars(
            select(TimeSession)
            .where(TimeSession.status == "done")
            .where(TimeSession.created_at >= start_dt)
        ).all()
    )
    # Also count sessions marked done via remaining==0 even if updated recently;
    # primary signal is status=done. Duration credited = duration_sec - remaining
    # (or full duration_sec when remaining is 0).
    by_day: dict[date, int] = {}
    total_sec = 0
    for ts in sessions:
        spent = int(ts.duration_sec or 0) - int(ts.remaining_sec or 0)
        if spent <= 0:
            spent = int(ts.duration_sec or 0)
        spent = max(0, spent)
        total_sec += spent
        day = (ts.created_at.date() if ts.created_at else today)
        by_day[day] = by_day.get(day, 0) + spent

    points: list[DailyPoint] = []
    for i in range(days):
        d = start + timedelta(days=i)
        # DailyPoint.completed stores minutes for focus bars
        points.append(DailyPoint(day=d, completed=round(by_day.get(d, 0) / 60)))

    return WeeklyFocusStats(
        sessions_count=len(sessions),
        total_sec=total_sec,
        total_min=round(total_sec / 60),
        days=points,
    )



def recent_focus_notes(session: Session, limit: int = 5) -> list[FocusNoteSnippet]:
    """Last N completed focus sessions that have a non-empty note (title + snippet)."""
    limit = max(1, min(20, int(limit or 5)))
    rows = list(
        session.scalars(
            select(TimeSession)
            .where(TimeSession.status == "done")
            .where(TimeSession.note.isnot(None), TimeSession.note != "")
            .order_by(TimeSession.created_at.desc(), TimeSession.id.desc())
            .limit(limit * 3)
        ).all()
    )
    out: list[FocusNoteSnippet] = []
    for ts in rows:
        note = (getattr(ts, "note", None) or "").strip()
        if not note:
            continue
        title = (ts.label or "").strip() or "Фокус"
        snippet = note if len(note) <= 120 else (note[:117].rstrip() + "…")
        out.append(
            FocusNoteSnippet(
                session_id=int(ts.id),
                title=title,
                note_snippet=snippet,
            )
        )
        if len(out) >= limit:
            break
    return out


def goal_forecasts(session: Session) -> list[GoalForecast]:
    """Active goals with days_to_complete estimate (quota pace)."""
    from app.services import goal_service

    out: list[GoalForecast] = []
    for g in goal_service.list_goals(session, archived=False):
        remaining = max(0.0, float(g.target_value) - float(g.current_value or 0.0))
        out.append(
            GoalForecast(
                goal_id=g.id,
                title=g.title,
                days_to_complete=goal_service.days_to_complete(g),
                percent_complete=float(g.percent_complete),
                daily_quota=float(g.daily_quota or 0.0),
                unit=g.unit or "units",
                remaining=remaining,
            )
        )
    # Soonest unfinished first; completed (0) at end; unknown (None) last among unfinished
    def _key(f: GoalForecast):
        d = f.days_to_complete
        if d is None:
            return (2, 10**9, f.title)
        if d == 0:
            return (1, 0, f.title)
        return (0, d, f.title)

    out.sort(key=_key)
    return out


def _week_bounds(
    today: date | None = None, *, week_starts_monday: bool = True
) -> tuple[date, date]:
    today = today or date.today()
    if week_starts_monday:
        start = today - timedelta(days=today.weekday())
    else:
        start = today - timedelta(days=(today.weekday() + 1) % 7)
    end = start + timedelta(days=6)
    return start, end


def weekly_review(
    session: Session,
    *,
    today: date | None = None,
    week_starts_monday: bool = True,
) -> WeeklyReview:
    """Calendar-week rollup: completed tasks, focus min, quota-met days, best streak."""
    from app.services import goal_service, streak_service

    start, end = _week_bounds(today, week_starts_monday=week_starts_monday)
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.max.time())

    completed_count = (
        session.scalar(
            select(func.count(Task.id))
            .where(Task.status == "done")
            .where(Task.archived.is_(False))
            .where(Task.completed_at.is_not(None))
            .where(Task.completed_at >= start_dt)
            .where(Task.completed_at <= end_dt)
        )
        or 0
    )

    sessions = list(
        session.scalars(
            select(TimeSession)
            .where(TimeSession.status == "done")
            .where(TimeSession.created_at >= start_dt)
            .where(TimeSession.created_at <= end_dt)
        ).all()
    )
    total_sec = 0
    for ts in sessions:
        spent = int(ts.duration_sec or 0) - int(ts.remaining_sec or 0)
        if spent <= 0:
            spent = int(ts.duration_sec or 0)
        total_sec += max(0, spent)
    focus_min = round(total_sec / 60)

    goals = goal_service.list_goals(session, archived=False)
    quotas_met_days = 0
    day = start
    while day <= end:
        for g in goals:
            quota = float(g.daily_quota or 0.0)
            if quota <= 0:
                continue
            logged = float(goal_service.today_logged(session, g.id, day=day) or 0.0)
            if logged >= quota:
                quotas_met_days += 1
        day += timedelta(days=1)

    streaks = streak_service.all_streaks(session)
    best_streak = max((s.current_streak for s in streaks), default=0) if streaks else 0

    return WeeklyReview(
        week_start=start,
        week_end=end,
        completed_count=int(completed_count),
        focus_min=int(focus_min),
        quotas_met_days=int(quotas_met_days),
        best_streak=int(best_streak),
    )


def count_completed_iso_week(
    session: Session, *, today: date | None = None
) -> int:
    """Count non-archived done tasks with completed_at in the current ISO week (Mon–Sun).

    ISO weeks always start Monday — independent of week_starts_monday setting.
    """
    today = today or date.today()
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=6)
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.max.time())
    n = (
        session.scalar(
            select(func.count(Task.id))
            .where(Task.status == "done")
            .where(Task.archived.is_(False))
            .where(Task.completed_at.is_not(None))
            .where(Task.completed_at >= start_dt)
            .where(Task.completed_at <= end_dt)
        )
        or 0
    )
    return int(n)


def weekly_goal_progress(
    session: Session, *, today: date | None = None
) -> tuple[int, int]:
    """Return (completed_this_iso_week, weekly_task_target) for Home/Analytics bar.

    Target comes from app_meta weekly_task_target (default 10).
    """
    from app.services import settings_service

    settings = settings_service.get_settings(session)
    try:
        target = int(getattr(settings, "weekly_task_target", 10) or 10)
    except (TypeError, ValueError):
        target = 10
    target = max(1, min(200, target))
    done = count_completed_iso_week(session, today=today)
    return done, target


def compute_momentum_score(
    *,
    quotas_met: int,
    quotas_total: int,
    done_tasks: int,
    total_tasks: int,
    best_streak: int,
    streak_cap: int = 14,
    w_quotas: float = 0.40,
    w_completion: float = 0.40,
    w_streak: float = 0.20,
) -> MomentumScore:
    """Pure 0–100 mix of today quotas met %, task completion rate, capped best streak.

    Weights default to 40 / 40 / 20. Empty quotas or tasks count as 100% for that leg
    so a fresh install is not punished. ``best_streak`` is scaled to ``streak_cap``.
    """
    cap = max(1, int(streak_cap))
    if quotas_total > 0:
        quotas_pct = 100.0 * max(0, int(quotas_met)) / float(quotas_total)
    else:
        quotas_pct = 100.0
    if total_tasks > 0:
        completion_pct = 100.0 * max(0, int(done_tasks)) / float(total_tasks)
    else:
        completion_pct = 100.0
    streak_pct = min(100.0, 100.0 * max(0, int(best_streak)) / float(cap))
    raw = (
        float(w_quotas) * quotas_pct
        + float(w_completion) * completion_pct
        + float(w_streak) * streak_pct
    )
    score = int(round(max(0.0, min(100.0, raw))))
    return MomentumScore(
        score=score,
        quotas_pct=round(quotas_pct, 1),
        completion_pct=round(completion_pct, 1),
        streak_pct=round(streak_pct, 1),
        best_streak=max(0, int(best_streak)),
        streak_cap=cap,
    )


def momentum_score(session: Session, *, streak_cap: int = 14) -> MomentumScore:
    """Session wrapper: today quotas + overview completion + best streak."""
    from app.services import goal_service, streak_service

    quotas = goal_service.today_quotas(session)
    met = sum(1 for q in quotas if q.get("complete"))
    stats = overview_stats(session)
    streaks = streak_service.all_streaks(session)
    best = max((s.best_streak for s in streaks), default=0) if streaks else 0
    return compute_momentum_score(
        quotas_met=met,
        quotas_total=len(quotas),
        done_tasks=stats.done_tasks,
        total_tasks=stats.total_tasks,
        best_streak=best,
        streak_cap=streak_cap,
    )


def stuck_goals(
    session: Session,
    *,
    days: int = 3,
    today: date | None = None,
) -> list[StuckGoal]:
    """Active incomplete goals with no ProgressLog in the last ``days`` calendar days.

    A goal is stuck when ``current_value < target_value``, not archived, and either
    has never been logged or its latest ``logged_at`` date is at least ``days`` ago
    (``(today - last.date()).days >= days``).
    """
    from app.services import goal_service

    today = today or date.today()
    days = max(1, int(days))
    goals = goal_service.list_goals(session, archived=False)
    incomplete = [
        g
        for g in goals
        if float(g.current_value or 0.0) < float(g.target_value or 0.0)
    ]
    if not incomplete:
        return []

    ids = [g.id for g in incomplete]
    rows = session.execute(
        select(ProgressLog.goal_id, func.max(ProgressLog.logged_at))
        .where(ProgressLog.goal_id.in_(ids))
        .group_by(ProgressLog.goal_id)
    ).all()
    last_by: dict[int, datetime] = {}
    for gid, last_at in rows:
        if last_at is None:
            continue
        last_by[int(gid)] = last_at

    out: list[StuckGoal] = []
    for g in incomplete:
        last = last_by.get(g.id)
        if last is None:
            created = getattr(g, "created_at", None)
            if isinstance(created, datetime):
                idle = (today - created.date()).days
            elif isinstance(created, date):
                idle = (today - created).days
            else:
                idle = days  # unknown create time → treat as threshold
            if idle < days:
                continue
            out.append(
                StuckGoal(
                    goal_id=g.id,
                    title=g.title,
                    days_idle=int(idle),
                    percent_complete=float(g.percent_complete),
                    last_logged_at=None,
                )
            )
            continue
        last_day = last.date() if isinstance(last, datetime) else last
        idle = (today - last_day).days
        if idle >= days:
            out.append(
                StuckGoal(
                    goal_id=g.id,
                    title=g.title,
                    days_idle=int(idle),
                    percent_complete=float(g.percent_complete),
                    last_logged_at=last if isinstance(last, datetime) else None,
                )
            )

    out.sort(key=lambda s: (-s.days_idle, s.title))
    return out


def daily_wrap(session: Session, *, today: date | None = None) -> DailyWrap:
    """Today snapshot for Home «Итог дня»: quotas met, tasks done, focus min, tip tomorrow."""
    from app.services import goal_service, settings_service

    today = today or date.today()
    start_dt = datetime.combine(today, datetime.min.time())
    end_dt = datetime.combine(today, datetime.max.time())

    quotas = goal_service.today_quotas(session)
    quotas_met = sum(1 for q in quotas if q.get("complete"))
    quotas_total = len(quotas)

    tasks_done = int(
        session.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.status == "done")
            .where(Task.completed_at.is_not(None))
            .where(Task.completed_at >= start_dt)
            .where(Task.completed_at <= end_dt)
        )
        or 0
    )

    focus = weekly_focus_stats(session, days=1)
    focus_min = int(focus.total_min or 0)
    if focus.days:
        last = focus.days[-1]
        if last.day == today:
            focus_min = int(last.completed or 0)

    tip = settings_service.get_tomorrow_home_tip(session)

    return DailyWrap(
        day=today,
        quotas_met=int(quotas_met),
        quotas_total=int(quotas_total),
        tasks_done=int(tasks_done),
        focus_min=int(focus_min),
        tip_tomorrow=tip or "",
    )

def _short_title(title: str, n: int = 28) -> str:
    t = (title or "").strip() or "цель"
    return t if len(t) <= n else t[: n - 1] + "…"


def compute_smart_suggestion(
    *,
    stuck: list | None = None,
    overdue_count: int = 0,
    incomplete_quotas: list[tuple[str, int]] | None = None,
) -> SmartSuggestion | None:
    """Priority: stuck goal log → overdue Tasks → first incomplete quota."""
    stuck = list(stuck or [])
    incomplete_quotas = list(incomplete_quotas or [])
    try:
        overdue_count = int(overdue_count or 0)
    except (TypeError, ValueError):
        overdue_count = 0
    if stuck:
        sg = stuck[0]
        title = _short_title(getattr(sg, "title", "") or "")
        try:
            idle = int(getattr(sg, "days_idle", 0) or 0)
        except (TypeError, ValueError):
            idle = 0
        try:
            gid = int(getattr(sg, "goal_id", 0) or 0) or None
        except (TypeError, ValueError):
            gid = None
        return SmartSuggestion(
            kind="stuck",
            text=f"Цель «{title}» без лога {idle} дн — запишите прогресс.",
            goal_id=gid,
        )
    if overdue_count > 0:
        return SmartSuggestion(
            kind="overdue",
            text=f"Есть {overdue_count} просроченных — откройте Задачи.",
        )
    if incomplete_quotas:
        raw_title, raw_gid = incomplete_quotas[0]
        try:
            gid = int(raw_gid) if raw_gid is not None else None
        except (TypeError, ValueError):
            gid = None
        return SmartSuggestion(
            kind="quota",
            text=(
                f"Квота «{_short_title(str(raw_title))}» ещё не закрыта "
                "— залогируйте сегодня."
            ),
            goal_id=gid,
        )
    return None


def smart_suggestion(session: Session) -> SmartSuggestion | None:
    """Contextual Home tip; None when dismissed today or nothing to suggest."""
    from app.services import goal_service, settings_service, task_service

    if settings_service.is_smart_suggest_dismissed(session):
        return None
    stuck = stuck_goals(session, days=3)
    overdue = [
        t
        for t in task_service.list_tasks(session, archived=False)
        if task_service.is_overdue(t)
    ]
    quotas = goal_service.today_quotas(session)
    incomplete = [
        (q["goal"].title, q["goal"].id)
        for q in quotas
        if not q.get("complete")
    ]
    return compute_smart_suggestion(
        stuck=stuck,
        overdue_count=len(overdue),
        incomplete_quotas=incomplete,
    )


def morning_briefing(session: Session, *, today: date | None = None) -> MorningBriefing:
    """Home «Брифинг»: overdue, due today, open quotas, momentum, one suggestion.

    Aggregates existing helpers. Suggestion is always computed (Home dismiss
    does not hide it — the user opened the dialog on purpose).
    """
    from app.services import goal_service, task_service

    today = today or date.today()
    active = task_service.list_tasks(session, archived=False)
    overdue_count = sum(1 for t in active if task_service.is_overdue(t, today=today))
    due_today = sum(1 for t in active if task_service.is_due_today(t, today=today))

    quotas = goal_service.today_quotas(session)
    incomplete = [
        IncompleteQuota(
            goal_id=int(q["goal"].id),
            title=q["goal"].title,
            today=float(q.get("today") or 0.0),
            quota=float(q.get("quota") or 0.0),
        )
        for q in quotas
        if not q.get("complete")
    ]

    momentum = momentum_score(session)
    stuck = stuck_goals(session, days=3, today=today)
    suggestion = compute_smart_suggestion(
        stuck=stuck,
        overdue_count=overdue_count,
        incomplete_quotas=[(q.title, q.goal_id) for q in incomplete],
    )
    return MorningBriefing(
        day=today,
        overdue_count=int(overdue_count),
        due_today=int(due_today),
        incomplete_quotas=incomplete,
        momentum=momentum,
        suggestion=suggestion,
    )

def tomorrow_plan(session: Session, *, today: date | None = None) -> TomorrowPlan:
    """Home «Завтра»: tasks due tomorrow + unfinished due today (carry hint)."""
    from app.services import task_service

    today = today or date.today()
    tomorrow = today + timedelta(days=1)
    active = task_service.list_tasks(session, archived=False)

    def _item(t) -> TomorrowPlanItem:
        return TomorrowPlanItem(
            task_id=int(t.id),
            title=t.title,
            priority=getattr(t, "priority", None) or "medium",
            estimated_min=getattr(t, "estimated_min", None),
        )

    due_tmr = [
        _item(t)
        for t in active
        if task_service.is_due_tomorrow(t, today=today)
    ]
    # pin/priority-ish: high first then medium then low, title
    prio_rank = {"high": 0, "medium": 1, "low": 2}
    due_tmr.sort(key=lambda x: (prio_rank.get(x.priority, 9), x.title.lower()))

    open_today = [
        _item(t)
        for t in active
        if task_service.is_due_today(t, today=today)
    ]
    open_today.sort(key=lambda x: (prio_rank.get(x.priority, 9), x.title.lower()))

    n_tmr = len(due_tmr)
    n_open = len(open_today)
    if n_tmr == 0 and n_open == 0:
        tip = "На завтра пока пусто — можно спокойно планировать."
    elif n_tmr == 0 and n_open:
        tip = (
            f"На завтра сроков нет, но сегодня ещё открыто: {n_open}. "
            "Перенесите лишнее на завтра или закройте сегодня."
        )
    elif n_tmr and n_open == 0:
        tip = f"Завтра уже {n_tmr} задач(и) — подготовьте фокус заранее."
    else:
        tip = (
            f"Завтра {n_tmr}, сегодня ещё {n_open} открытых. "
            "Закройте сегодняшнее, чтобы не тащить хвост."
        )

    return TomorrowPlan(
        day=tomorrow,
        due_tomorrow=due_tmr,
        open_today=open_today,
        tip=tip,
    )

