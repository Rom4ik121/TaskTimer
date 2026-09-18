"""App settings stored in app_meta."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.db import get_meta, set_meta
from app.schemas import SettingsOut, SettingsUpdate

DEFAULTS = SettingsOut()


def _parse_int(raw: str | None, default: int, *, lo: int, hi: int) -> int:
    try:
        v = int(str(raw).strip()) if raw is not None else default
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def get_settings(session: Session) -> SettingsOut:
    name = get_meta(session, "display_name") or DEFAULTS.display_name
    accent = get_meta(session, "accent_hex") or DEFAULTS.accent_hex
    week = get_meta(session, "week_starts_monday")
    week_mon = True if week is None else week in ("1", "true", "True", "yes")
    work = _parse_int(
        get_meta(session, "pomodoro_work_min"),
        DEFAULTS.pomodoro_work_min,
        lo=5,
        hi=90,
    )
    brk = _parse_int(
        get_meta(session, "pomodoro_break_min"),
        DEFAULTS.pomodoro_break_min,
        lo=1,
        hi=30,
    )
    arch_raw = get_meta(session, "archive_on_recur_done")
    archive_on_recur = (
        False
        if arch_raw is None
        else str(arch_raw).strip().lower() in ("1", "true", "yes", "on")
    )
    quiet_start = _parse_int(
        get_meta(session, "quiet_start"), DEFAULTS.quiet_start, lo=0, hi=23
    )
    quiet_end = _parse_int(
        get_meta(session, "quiet_end"), DEFAULTS.quiet_end, lo=0, hi=23
    )
    ac_raw = get_meta(session, "auto_complete_subtasks")
    auto_complete = (
        False
        if ac_raw is None
        else str(ac_raw).strip().lower() in ("1", "true", "yes", "on")
    )
    compact_raw = get_meta(session, "compact_ui")
    compact_ui = (
        False
        if compact_raw is None
        else str(compact_raw).strip().lower() in ("1", "true", "yes", "on")
    )
    haptics_raw = get_meta(session, "haptics_enabled")
    haptics_enabled = (
        True
        if haptics_raw is None
        else str(haptics_raw).strip().lower() in ("1", "true", "yes", "on")
    )
    wind_down = _parse_int(
        get_meta(session, "wind_down_hour"),
        DEFAULTS.wind_down_hour,
        lo=0,
        hi=23,
    )
    weekly_target = _parse_int(
        get_meta(session, "weekly_task_target"),
        DEFAULTS.weekly_task_target,
        lo=1,
        hi=200,
    )
    return SettingsOut(
        display_name=name,
        accent_hex=accent if accent.startswith("#") else f"#{accent}",
        week_starts_monday=week_mon,
        pomodoro_work_min=work,
        pomodoro_break_min=brk,
        archive_on_recur_done=archive_on_recur,
        quiet_start=quiet_start,
        quiet_end=quiet_end,
        auto_complete_subtasks=auto_complete,
        compact_ui=compact_ui,
        haptics_enabled=haptics_enabled,
        wind_down_hour=wind_down,
        weekly_task_target=weekly_target,
    )


def update_settings(session: Session, data: SettingsUpdate) -> SettingsOut:
    payload = data.model_dump(exclude_unset=True)
    if "display_name" in payload and payload["display_name"] is not None:
        set_meta(session, "display_name", str(payload["display_name"]).strip())
    if "accent_hex" in payload and payload["accent_hex"] is not None:
        set_meta(session, "accent_hex", str(payload["accent_hex"]))
    if "week_starts_monday" in payload and payload["week_starts_monday"] is not None:
        set_meta(
            session,
            "week_starts_monday",
            "1" if payload["week_starts_monday"] else "0",
        )
    if "pomodoro_work_min" in payload and payload["pomodoro_work_min"] is not None:
        set_meta(session, "pomodoro_work_min", str(int(payload["pomodoro_work_min"])))
    if "pomodoro_break_min" in payload and payload["pomodoro_break_min"] is not None:
        set_meta(session, "pomodoro_break_min", str(int(payload["pomodoro_break_min"])))
    if "archive_on_recur_done" in payload and payload["archive_on_recur_done"] is not None:
        set_meta(
            session,
            "archive_on_recur_done",
            "1" if payload["archive_on_recur_done"] else "0",
        )
    if "quiet_start" in payload and payload["quiet_start"] is not None:
        set_meta(session, "quiet_start", str(int(payload["quiet_start"])))
    if "quiet_end" in payload and payload["quiet_end"] is not None:
        set_meta(session, "quiet_end", str(int(payload["quiet_end"])))
    if "auto_complete_subtasks" in payload and payload["auto_complete_subtasks"] is not None:
        set_meta(
            session,
            "auto_complete_subtasks",
            "1" if payload["auto_complete_subtasks"] else "0",
        )
    if "compact_ui" in payload and payload["compact_ui"] is not None:
        set_meta(
            session,
            "compact_ui",
            "1" if payload["compact_ui"] else "0",
        )
    if "haptics_enabled" in payload and payload["haptics_enabled"] is not None:
        set_meta(
            session,
            "haptics_enabled",
            "1" if payload["haptics_enabled"] else "0",
        )
    if "wind_down_hour" in payload and payload["wind_down_hour"] is not None:
        set_meta(session, "wind_down_hour", str(int(payload["wind_down_hour"])))
    if "weekly_task_target" in payload and payload["weekly_task_target"] is not None:
        set_meta(session, "weekly_task_target", str(int(payload["weekly_task_target"])))
    session.commit()
    return get_settings(session)


def is_quiet_hours(
    settings: SettingsOut | None = None,
    *,
    hour: Optional[int] = None,
    now: Optional[datetime] = None,
    quiet_start: Optional[int] = None,
    quiet_end: Optional[int] = None,
) -> bool:
    """True when local hour is inside [quiet_start, quiet_end) wrapping midnight.

    Defaults 22→8: quiet for hours 22,23,0,…,7. Equal start/end means always quiet.
    Safe when settings/meta fields are missing.
    """
    def _hour_val(raw, default: int) -> int:
        try:
            if raw is None:
                return default
            return max(0, min(23, int(raw)))
        except (TypeError, ValueError):
            return default

    if settings is not None:
        qs = _hour_val(getattr(settings, "quiet_start", None), DEFAULTS.quiet_start)
        qe = _hour_val(getattr(settings, "quiet_end", None), DEFAULTS.quiet_end)
    else:
        qs = _hour_val(quiet_start, DEFAULTS.quiet_start)
        qe = _hour_val(quiet_end, DEFAULTS.quiet_end)
    if hour is None:
        hour = (now or datetime.now()).hour
    try:
        hour = int(hour) % 24
    except (TypeError, ValueError):
        hour = (now or datetime.now()).hour % 24
    if qs == qe:
        return True
    if qs < qe:
        return qs <= hour < qe
    # wraps midnight, e.g. 22→8
    return hour >= qs or hour < qe


def is_wind_down(
    settings: SettingsOut | None = None,
    *,
    hour: Optional[int] = None,
    now: Optional[datetime] = None,
    wind_down_hour: Optional[int] = None,
) -> bool:
    """True when local hour >= wind_down_hour (default 18). Soft evening mode, not a block.

    Safe when settings/meta fields are missing or corrupt.
    """
    def _hour_val(raw, default: int) -> int:
        try:
            if raw is None:
                return default
            return max(0, min(23, int(raw)))
        except (TypeError, ValueError):
            return default

    if settings is not None:
        wd = _hour_val(getattr(settings, "wind_down_hour", None), DEFAULTS.wind_down_hour)
    else:
        wd = _hour_val(wind_down_hour, DEFAULTS.wind_down_hour)
    if hour is None:
        hour = (now or datetime.now()).hour
    try:
        hour = int(hour) % 24
    except (TypeError, ValueError):
        hour = (now or datetime.now()).hour % 24
    return hour >= wd


def is_onboarded(session: Session) -> bool:
    """True when first-run onboarding has been completed."""
    return get_meta(session, "onboarded") == "1"


def mark_onboarded(session: Session) -> None:
    set_meta(session, "onboarded", "1")
    session.commit()


def clear_onboarded(session: Session) -> None:
    """Reset so Home / Settings can show the onboarding sheet again."""
    set_meta(session, "onboarded", "0")
    session.commit()


HOME_TIPS: list[str] = [
    "Закрывайте дневную квоту — серии растут каждый день 🔥",
    "Закрепите важные задачи — они всегда сверху на Доме",
    "Тихие часы скрывают баннеры напоминаний ночью",
    "Экспортируйте JSON в Настройках перед крупными изменениями",
    "Фокус-таймер считает минуты в аналитике за неделю",
]


def get_daily_home_tip(session: Session) -> str:
    """Rotate among HOME_TIPS once per calendar day; persist index in app_meta.

    Safe when home_tip_* meta keys are missing or corrupt.
    """
    tips = HOME_TIPS
    n = len(tips)
    if n == 0:
        return ""
    today = date.today().isoformat()
    tip_day = get_meta(session, "home_tip_day")
    raw_idx = get_meta(session, "home_tip_index")
    try:
        idx = int(raw_idx) if raw_idx is not None and str(raw_idx).strip() != "" else 0
    except (TypeError, ValueError):
        idx = 0
    idx = idx % n
    if not tip_day or tip_day != today:
        if tip_day and tip_day != today:
            idx = (idx + 1) % n
        try:
            set_meta(session, "home_tip_index", str(idx))
            set_meta(session, "home_tip_day", today)
            session.commit()
        except Exception:
            # meta write failure must not crash Home
            pass
    return tips[idx]


def get_tomorrow_home_tip(session: Session) -> str:
    """Peek the next HOME_TIPS entry (what tomorrow's rotation would show).

    Does not write meta. Safe when tip meta is missing/corrupt.
    """
    tips = HOME_TIPS
    n = len(tips)
    if n == 0:
        return ""
    raw_idx = get_meta(session, "home_tip_index")
    try:
        idx = int(raw_idx) if raw_idx is not None and str(raw_idx).strip() != "" else 0
    except (TypeError, ValueError):
        idx = 0
    nxt = (idx + 1) % n
    return tips[nxt]

SMART_SUGGEST_DISMISS_KEY = "smart_suggest_dismissed"


def _as_today(today: date | datetime | str | None) -> date:
    """Normalize today arg; never raise — fall back to ``date.today()``."""
    if today is None:
        return date.today()
    if isinstance(today, datetime):
        return today.date()
    if isinstance(today, date):
        return today
    raw = str(today).strip()
    if not raw:
        return date.today()
    try:
        # Accept YYYY-MM-DD or ISO datetime prefix
        return date.fromisoformat(raw[:10])
    except (TypeError, ValueError):
        return date.today()


def _parse_dismiss_day(raw: str | None) -> date | None:
    """Parse meta dismiss value → date, or None if missing/corrupt."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # booleans / junk flags from older experiments
    if s.lower() in ("1", "0", "true", "false", "yes", "no", "on", "off"):
        return None
    try:
        return date.fromisoformat(s[:10])
    except (TypeError, ValueError):
        return None


def is_smart_suggest_dismissed(
    session: Session, *, today: date | datetime | str | None = None
) -> bool:
    """True when the Home smart tip was dismissed for ``today`` (ISO in meta).

    Edge cases: missing/empty/corrupt meta → False; past dismiss day → False;
    boolean junk → False; ISO datetime prefix accepted; ``today`` normalized.
    """
    day = _as_today(today)
    try:
        raw = get_meta(session, SMART_SUGGEST_DISMISS_KEY)
    except Exception:
        return False
    stored = _parse_dismiss_day(raw)
    if stored is None:
        return False
    return stored == day


def dismiss_smart_suggest(
    session: Session, *, today: date | datetime | str | None = None
) -> None:
    """Hide the smart tip for the rest of today. Idempotent; safe on write fail.

    Double-dismiss and already-dismissed-today are no-ops. Corrupt previous
    values are overwritten with a clean ISO date.
    """
    day = _as_today(today)
    iso = day.isoformat()
    try:
        raw = get_meta(session, SMART_SUGGEST_DISMISS_KEY)
        # Already clean for today → no-op; otherwise normalize / write
        if str(raw or "").strip() == iso:
            return
        set_meta(session, SMART_SUGGEST_DISMISS_KEY, iso)
        session.commit()
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass


def clear_smart_suggest_dismiss(session: Session) -> None:
    """Clear dismiss flag so the tip can show again (tests / day rollover)."""
    try:
        set_meta(session, SMART_SUGGEST_DISMISS_KEY, "")
        session.commit()
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass


def _daily_note_key(day: date | None = None) -> str:
    d = day or date.today()
    return f"daily_note_{d.isoformat()}"


def get_daily_note(session: Session, day: date | None = None) -> str:
    """Return the daily note text for ``day`` (default today), or empty string."""
    raw = get_meta(session, _daily_note_key(day))
    return raw if raw is not None else ""


def set_daily_note(session: Session, text: str, day: date | None = None) -> str:
    """Persist daily note; returns the stored text (stripped trailing only kept as-is)."""
    value = text if text is not None else ""
    set_meta(session, _daily_note_key(day), value)
    session.commit()
    return value
