"""Settings overlay — display name, accent presets, export / import, soft undo."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import flet as ft
from pydantic import ValidationError

from app.db import SCHEMA_VERSION, get_db_path, get_session
from app.schemas import SettingsUpdate
from app.services import export_service, goal_service, lock_service, settings_service, streak_service
from app.ui.components.cards import empty_state
from app.ui.components.dialogs import (
    confirm_delete,
    ru_validation_message,
    set_field_error,
    show_info,
    show_snack,
    show_toast,
    validation_fail,
)
from app.ui.haptics import haptic, set_enabled
from app.ui.screens.onboarding import clear_onboarded, show_onboarding
from app.ui.theme import (
    ACCENT_PRESETS,
    BORDER,
    MUTED,
    ORANGE,
    TEXT,
    apply_accent,
    card_style,
    group_heading,
    muted,
    screen_header,
    screen_insets,
)


APP_VERSION = "1.0"
# Numbered capabilities in README (Waves A–AV), kept in sync with feature_matrix.
FEATURE_COUNT = 77


def _readme_path() -> Path:
    return Path(__file__).resolve().parents[3] / "README.md"


def build_settings(
    page: ft.Page,
    *,
    on_back,
    refresh_all,
    on_setup_pin=None,
    on_change_pin=None,
) -> ft.Control:
    with get_session() as session:
        s = settings_service.get_settings(session)
        undo_path = export_service.get_last_import_backup(session)
        last_exp_path, last_exp_at = export_service.get_last_export(session)
        freeze_active = streak_service.is_freeze_active(session)
        freeze_week = streak_service.iso_week_key()
        lock_on = lock_service.is_lock_enabled(session)
        has_pin = lock_service.has_pin(session)
        bio_on = lock_service.is_biometrics_enabled(session)

    name_field = ft.TextField(
        label="Имя",
        value=s.display_name,
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
    )
    accent_field = ft.TextField(
        label="Акцент (hex)",
        value=s.accent_hex,
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
        expand=True,
    )
    week_sw = ft.Switch(
        label="Неделя с понедельника",
        value=s.week_starts_monday,
        active_color=ORANGE,
    )
    archive_recur_sw = ft.Switch(
        label="Архивировать после повтора",
        value=bool(s.archive_on_recur_done),
        active_color=ORANGE,
    )
    auto_complete_sw = ft.Switch(
        label="Завершать задачу, когда все подзадачи готовы",
        value=bool(getattr(s, "auto_complete_subtasks", False)),
        active_color=ORANGE,
    )
    compact_sw = ft.Switch(
        label="Компактный режим",
        value=bool(getattr(s, "compact_ui", False)),
        active_color=ORANGE,
    )
    haptics_sw = ft.Switch(
        label="Тактильность",
        value=bool(getattr(s, "haptics_enabled", True)),
        active_color=ORANGE,
    )
    lock_sw = ft.Switch(
        label="Блокировка PIN",
        value=bool(lock_on),
        active_color=ORANGE,
    )
    bio_sw = ft.Switch(
        label="Face ID / биометрия",
        value=bool(bio_on),
        active_color=ORANGE,
    )
    work_field = ft.TextField(
        label="Помодоро · работа (мин)",
        value=str(s.pomodoro_work_min),
        keyboard_type=ft.KeyboardType.NUMBER,
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
        expand=True,
    )
    break_field = ft.TextField(
        label="Помодоро · перерыв (мин)",
        value=str(s.pomodoro_break_min),
        keyboard_type=ft.KeyboardType.NUMBER,
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
        expand=True,
    )
    quiet_start_f = ft.TextField(
        label="Тихие часы · с (0–23)",
        value=str(s.quiet_start),
        keyboard_type=ft.KeyboardType.NUMBER,
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
        expand=True,
    )
    quiet_end_f = ft.TextField(
        label="Тихие часы · до (0–23)",
        value=str(s.quiet_end),
        keyboard_type=ft.KeyboardType.NUMBER,
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
        expand=True,
    )
    wind_down_f = ft.TextField(
        label="Вечерний режим · с (0–23)",
        value=str(getattr(s, "wind_down_hour", 18)),
        keyboard_type=ft.KeyboardType.NUMBER,
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
        expand=True,
    )
    weekly_target_f = ft.TextField(
        label="Цель недели · задач (1–200)",
        value=str(getattr(s, "weekly_task_target", 10)),
        keyboard_type=ft.KeyboardType.NUMBER,
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
        expand=True,
    )
    preview = ft.Container(
        width=48,
        height=48,
        bgcolor=s.accent_hex,
        border_radius=ft.BorderRadius.all(12),
        border=ft.Border.all(1, BORDER),
    )
    def _format_last_export(path_s: str | None, at_s: str | None) -> str:
        if not path_s and not at_s:
            return ""
        name = Path(path_s).name if path_s else "—"
        when = at_s or ""
        if when:
            return f"Последний экспорт: {name} · {when}"
        return f"Последний экспорт: {name}"

    export_info = ft.Text(
        _format_last_export(last_exp_path, last_exp_at),
        size=11,
        color=MUTED,
    )
    import_path = ft.TextField(
        label="Файл в data/ (export-….json)",
        hint_text="export-YYYYMMDD-HHMMSS.json",
        border_color=BORDER,
        focused_border_color=ORANGE,
        color=TEXT,
    )
    import_info = ft.Text("", size=11, color=MUTED)
    undo_info = ft.Text(
        f"Бэкап: {undo_path.name}" if undo_path else "Нет снимка для отмены",
        size=11,
        color=MUTED,
    )
    undo_btn_host = ft.Container()

    # FilePicker — keep strong refs so service registry does not GC it
    picker = ft.FilePicker()
    try:
        services = list(page.services or [])
        if picker not in services:
            services.append(picker)
            page.services = services
    except Exception:
        picker = None  # type: ignore[assignment]

    def _valid_hex(raw: str) -> str | None:
        raw = (raw or "").strip()
        if raw and not raw.startswith("#"):
            raw = "#" + raw
        try:
            SettingsUpdate(accent_hex=raw)
            return raw.upper() if len(raw) == 7 else raw
        except Exception:
            return None

    def _paint_live(hx: str) -> None:
        preview.bgcolor = hx
        apply_accent(hx, page)
        accent_field.value = hx
        accent_field.focused_border_color = hx
        week_sw.active_color = hx
        archive_recur_sw.active_color = hx
        auto_complete_sw.active_color = hx
        compact_sw.active_color = hx
        lock_sw.active_color = hx
        bio_sw.active_color = hx
        name_field.focused_border_color = hx
        work_field.focused_border_color = hx
        break_field.focused_border_color = hx
        quiet_start_f.focused_border_color = hx
        quiet_end_f.focused_border_color = hx
        wind_down_f.focused_border_color = hx
        weekly_target_f.focused_border_color = hx
        import_path.focused_border_color = hx

    def refresh_preview(_=None):
        hx = _valid_hex(accent_field.value or "")
        if hx:
            _paint_live(hx)
        page.update()

    accent_field.on_change = refresh_preview

    def pick_preset(hex_color: str):
        def _on(_e=None):
            hx = _valid_hex(hex_color) or hex_color
            _paint_live(hx)
            page.update()

        return _on

    preset_chips = ft.Row(
        [
            ft.Container(
                content=ft.Text(
                    label[:1].upper(),
                    size=11,
                    weight=ft.FontWeight.W_700,
                    color="#0F0F12",
                ),
                width=36,
                height=36,
                bgcolor=hx,
                border_radius=ft.BorderRadius.all(18),
                alignment=ft.Alignment.CENTER,
                border=ft.Border.all(
                    2, TEXT if hx.upper() == (s.accent_hex or "").upper() else BORDER
                ),
                tooltip=f"{label} {hx}",
                on_click=pick_preset(hx),
                ink=True,
            )
            for label, hx in ACCENT_PRESETS
        ],
        spacing=10,
    )


    freeze_status = ft.Text(
        (
            f"Использована на неделе {freeze_week} — один пропуск квоты не рвёт текущую серию."
            if freeze_active
            else f"Доступна на неделе {freeze_week}: один раз защитить серию при пропуске дня."
        ),
        size=12,
        color=MUTED,
    )

    def do_streak_freeze(_e=None):
        with get_session() as session:
            ok = streak_service.activate_streak_freeze(session)
            week = streak_service.iso_week_key()
        if ok:
            freeze_status.value = (
                f"Использована на неделе {week} — один пропуск квоты не рвёт текущую серию."
            )
            freeze_btn.disabled = True
            freeze_btn.opacity = 0.55
            show_snack(page, "Серия защищена на эту неделю ❄️")
            refresh_all()
        else:
            show_snack(page, "Заморозка уже использована на этой неделе", error=True)
        page.update()

    freeze_btn = ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.AC_UNIT, color="#0F0F12", size=18),
                ft.Text(
                    "Заморозить серию",
                    size=14,
                    weight=ft.FontWeight.W_700,
                    color="#0F0F12",
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=8,
        ),
        bgcolor=ORANGE,
        padding=14,
        border_radius=ft.BorderRadius.all(14),
        on_click=do_streak_freeze,
        ink=True,
        disabled=freeze_active,
        opacity=0.55 if freeze_active else 1.0,
    )

    def on_lock_toggle(e):
        want = bool(e.control.value)
        with get_session() as session:
            if want and not lock_service.has_pin(session):
                lock_sw.value = False
                try:
                    page.update()
                except Exception:
                    pass
                if callable(on_setup_pin):
                    on_setup_pin()
                else:
                    show_snack(page, "Сначала задайте PIN", error=True)
                return
            lock_service.set_lock_enabled(session, want)
        show_snack(
            page,
            "Блокировка включена" if want else "Блокировка выключена",
        )

    lock_sw.on_change = on_lock_toggle

    def on_bio_toggle(e):
        want = bool(e.control.value)
        with get_session() as session:
            lock_service.set_biometrics_enabled(session, want)
        if want and not lock_service.is_biometrics_available():
            show_snack(page, lock_service.biometrics_unavailable_message())
        else:
            show_snack(
                page,
                "Face ID: предпочтение сохранено" if want else "Face ID выключен",
            )

    bio_sw.on_change = on_bio_toggle

    def do_change_pin(_e=None):
        if callable(on_change_pin):
            on_change_pin()
        else:
            show_snack(page, "Смена PIN недоступна", error=True)

    change_pin_btn = ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.PIN_OUTLINED, color=TEXT, size=18),
                ft.Text(
                    "Сменить PIN",
                    size=14,
                    weight=ft.FontWeight.W_700,
                    color=TEXT,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=8,
        ),
        bgcolor="#1C1C22",
        padding=14,
        border_radius=ft.BorderRadius.all(14),
        border=ft.Border.all(1, BORDER),
        on_click=do_change_pin,
        ink=True,
        visible=bool(has_pin),
    )

    def save(_):
        for fld in (
            name_field,
            accent_field,
            work_field,
            break_field,
            quiet_start_f,
            quiet_end_f,
            wind_down_f,
            weekly_target_f,
        ):
            set_field_error(fld, None)
        try:
            work_min = int(str(work_field.value or "25").strip())
            break_min = int(str(break_field.value or "5").strip())
            q_start = int(str(quiet_start_f.value or "22").strip())
            q_end = int(str(quiet_end_f.value or "8").strip())
            wd_hour = int(str(wind_down_f.value or "18").strip())
            weekly_tgt = int(str(weekly_target_f.value or "10").strip())
        except ValueError:
            validation_fail(page, "Минуты и часы — целые числа", work_field)
            return
        if not (0 <= q_start <= 23 and 0 <= q_end <= 23):
            validation_fail(page, "Тихие часы: час 0–23", quiet_start_f)
            return
        if not (0 <= wd_hour <= 23):
            validation_fail(page, "Вечерний режим: час 0–23", wind_down_f)
            return
        if not (1 <= weekly_tgt <= 200):
            validation_fail(page, "Цель недели: 1–200 задач", weekly_target_f)
            return
        try:
            data = SettingsUpdate(
                display_name=(name_field.value or "").strip() or "Рома",
                accent_hex=accent_field.value or "#FF8A00",
                week_starts_monday=bool(week_sw.value),
                pomodoro_work_min=work_min,
                pomodoro_break_min=break_min,
                archive_on_recur_done=bool(archive_recur_sw.value),
                auto_complete_subtasks=bool(auto_complete_sw.value),
                compact_ui=bool(compact_sw.value),
                haptics_enabled=bool(haptics_sw.value),
                quiet_start=q_start,
                quiet_end=q_end,
                wind_down_hour=wd_hour,
                weekly_task_target=weekly_tgt,
            )
        except ValidationError as exc:
            validation_fail(page, ru_validation_message(exc), name_field)
            return
        with get_session() as session:
            updated = settings_service.update_settings(session, data)
        set_enabled(bool(updated.haptics_enabled))
        apply_accent(updated.accent_hex, page)
        haptic(page, "success")
        show_toast(page, "Настройки сохранены", kind="success")
        refresh_all()

    def _export_to_data() -> Path:
        with get_session() as session:
            return export_service.write_export_file(session)

    def _snack_export(path: Path, data: dict | None = None) -> None:
        summary = export_service.summarize_export(data=data, path=path)
        show_snack(page, export_service.format_export_snack(summary, path.name))

    def do_export(_=None):
        path = _export_to_data()
        with get_session() as session:
            lp, la = export_service.get_last_export(session)
        export_info.value = _format_last_export(lp, la) or f"Сохранено: {path.name}"
        _snack_export(path)
        page.update()

    def do_export_csv(_=None):
        with get_session() as session:
            path = export_service.export_tasks_csv(session)
        show_snack(page, f"CSV: {path.name}")
        export_info.value = f"CSV: {path}"
        page.update()

    async def do_export_picker(_e=None):
        if picker is None:
            do_export()
            return
        with get_session() as session:
            data = export_service.export_all(session)
        payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        fname = f"export-{stamp}.json"
        try:
            saved = await picker.save_file(
                dialog_title="Экспорт TaskTimer",
                file_name=fname,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["json"],
                src_bytes=payload,
            )
        except Exception:
            do_export()
            return
        if not saved:
            # cancelled — still offer data/ fallback note
            export_info.value = "Отменено · можно сохранить в data/"
            page.update()
            return
        # Desktop may return path without writing when src_bytes used; ensure file
        try:
            p = Path(saved)
            if not p.exists() or p.stat().st_size == 0:
                p.write_bytes(payload)
            with get_session() as session:
                export_service.record_last_export(session, p)
                session.commit()
                lp, la = export_service.get_last_export(session)
            export_info.value = _format_last_export(lp, la) or f"Сохранено: {p.name}"
            _snack_export(p, data)
        except Exception:
            # last resort data/
            path = _export_to_data()
            with get_session() as session:
                lp, la = export_service.get_last_export(session)
            export_info.value = _format_last_export(lp, la) or f"Сохранено в data/: {path.name}"
            _snack_export(path)
        page.update()

    def _resolve_import_path() -> Path | None:
        raw = (import_path.value or "").strip()
        if not raw:
            return None
        p = Path(raw)
        if not p.is_absolute():
            p = get_db_path().parent / raw
        return p if p.exists() else None

    def _refresh_undo_ui():
        with get_session() as session:
            bak = export_service.get_last_import_backup(session)
        if bak:
            undo_info.value = f"Бэкап: {bak.name}"
            undo_btn_host.visible = True
            undo_btn_host.content = ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.UNDO_ROUNDED, color=TEXT, size=18),
                        ft.Text(
                            "Отменить импорт",
                            size=14,
                            weight=ft.FontWeight.W_700,
                            color=TEXT,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=8,
                ),
                bgcolor="#2A1C12",
                padding=14,
                border_radius=ft.BorderRadius.all(14),
                border=ft.Border.all(1, ORANGE),
                on_click=do_undo_import,
                ink=True,
            )
        else:
            undo_info.value = "Нет снимка для отмены"
            undo_btn_host.visible = False
            undo_btn_host.content = None

    def _run_import(mode: str | None):
        path = _resolve_import_path()
        if path is None:
            show_snack(page, "Файл не найден в data/", error=True)
            return
        try:
            with get_session() as session:
                summary = export_service.import_all(session, path, mode=mode)
                settings = settings_service.get_settings(session)
            apply_accent(settings.accent_hex, page)
            bak_note = ""
            if summary.get("pre_import_backup"):
                bak_note = " · undo snapshot"
            import_info.value = (
                f"Режим {summary['mode']}: +{summary['goals']} целей, "
                f"+{summary['tasks']} задач, "
                f"merge {summary['merged_goals']}/{summary['merged_tasks']}"
                f"{bak_note}"
            )
            show_snack(page, f"Импорт OK ({summary['mode']})")
            _refresh_undo_ui()
            refresh_all()
        except Exception as exc:
            show_snack(page, f"Импорт: {exc}", error=True)
            page.update()

    def do_import(_=None):
        path = _resolve_import_path()
        if path is None:
            data_dir = get_db_path().parent
            exports = sorted(data_dir.glob("export-*.json"), reverse=True)
            if exports and not (import_path.value or "").strip():
                import_path.value = exports[0].name
                page.update()
                path = exports[0]
            else:
                show_snack(page, "Укажите имя файла export-*.json в data/", error=True)
                return

        with get_session() as session:
            empty = export_service.is_content_empty(session)

        if empty:
            _run_import("replace")
            return

        def ask_mode():
            def merge(_e=None):
                page.pop_dialog()
                _run_import("merge")

            def replace(_e=None):
                page.pop_dialog()

                def yes():
                    _run_import("replace")

                confirm_delete(
                    page,
                    title="Заменить все данные?",
                    message=(
                        "Текущие задачи и цели будут удалены и заменены из бэкапа. "
                        "Перед заменой сохранится снимок для «Отменить импорт»."
                    ),
                    on_confirm=yes,
                )

            page.show_dialog(
                ft.AlertDialog(
                    title=ft.Text("Импорт бэкапа", color=TEXT),
                    content=ft.Text(
                        "База не пуста. Слить по названию (merge) или полностью заменить?",
                        color=MUTED,
                        size=13,
                    ),
                    actions=[
                        ft.TextButton("Отмена", on_click=lambda e: page.pop_dialog()),
                        ft.TextButton("Слить", on_click=merge),
                        ft.TextButton("Заменить", on_click=replace),
                    ],
                )
            )

        ask_mode()

    async def do_import_picker(_e=None):
        if picker is None:
            do_import()
            return
        try:
            files = await picker.pick_files(
                dialog_title="Импорт бэкапа TaskTimer",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["json"],
                allow_multiple=False,
                with_data=True,
            )
        except Exception:
            show_snack(page, "FilePicker недоступен — укажите путь вручную", error=True)
            return
        if not files:
            return
        f = files[0]
        target: Path | None = None
        if f.path:
            target = Path(f.path)
        elif f.bytes:
            data_dir = get_db_path().parent
            data_dir.mkdir(parents=True, exist_ok=True)
            target = data_dir / (f.name or "import-picked.json")
            target.write_bytes(f.bytes)
        if target is None or not target.exists():
            show_snack(page, "Не удалось прочитать файл", error=True)
            return
        # Prefer relative name when under data/
        try:
            rel = target.relative_to(get_db_path().parent)
            import_path.value = str(rel)
        except ValueError:
            import_path.value = str(target)
        page.update()
        do_import()

    def do_undo_import(_e=None):
        def yes():
            try:
                with get_session() as session:
                    summary = export_service.undo_last_replace_import(session)
                    settings = settings_service.get_settings(session)
                apply_accent(settings.accent_hex, page)
                import_info.value = (
                    f"Отмена импорта OK · восстановлено из снимка "
                    f"({summary.get('mode')})"
                )
                show_snack(page, "Импорт отменён — данные восстановлены")
                _refresh_undo_ui()
                refresh_all()
            except Exception as exc:
                show_snack(page, f"Отмена: {exc}", error=True)
                page.update()

        confirm_delete(
            page,
            title="Отменить последний replace-импорт?",
            message="Текущие данные будут заменены снимком, сделанным перед импортом.",
            on_confirm=yes,
        )

    def on_export_click(e):
        if picker is not None:
            page.run_task(do_export_picker, e)
        else:
            do_export(e)

    def on_import_click(e):
        # Prefer FilePicker; path field remains as fallback / after pick
        if picker is not None and not (import_path.value or "").strip():
            page.run_task(do_import_picker, e)
        else:
            do_import(e)

    pick_row = ft.Row(
        [
            ft.TextButton(
                "Выбрать файл…",
                icon=ft.Icons.FOLDER_OPEN_OUTLINED,
                on_click=lambda e: page.run_task(do_import_picker, e)
                if picker is not None
                else show_snack(page, "FilePicker недоступен", error=True),
                style=ft.ButtonStyle(color=ORANGE),
            ),
            ft.TextButton(
                "Сохранить как…",
                icon=ft.Icons.SAVE_ALT_OUTLINED,
                on_click=lambda e: page.run_task(do_export_picker, e)
                if picker is not None
                else do_export(e),
                style=ft.ButtonStyle(color=ORANGE),
            ),
        ],
        spacing=4,
    )

    _refresh_undo_ui()

    def replay_onboarding(_e=None):
        clear_onboarded()
        show_onboarding(page, force=True)


    def clear_celebrations(_e=None):
        def yes():
            with get_session() as session:
                n = goal_service.clear_celebrated_flags(session)
            show_snack(page, f"Сброшено celebration-флагов: {n}")
            page.update()

        confirm_delete(
            page,
            title="Сбросить celebration-флаги?",
            message=(
                "Удалит все celebrated_goal_* из meta. "
                "Можно снова увидеть 🎉 при достижении цели."
            ),
            on_confirm=yes,
            confirm_label="Сбросить",
        )

    def show_readme(_e=None):
        readme = _readme_path()
        uri = readme.resolve().as_uri()
        try:
            page.launch_url(uri)
            show_snack(page, f"README: {readme}")
        except Exception:
            show_snack(page, f"README: {readme}")


    SHORTCUT_HELP_LINES = [
        ("Ctrl+N — создать задачу (desktop / native Flet).", "item"),
        ("Ctrl+F — открыть поиск (desktop / native Flet).", "item"),
        ("Esc — закрыть оверлей (поиск / создать / настройки / фокус / деталь / напоминания / заметка), если фокус не в TextField. Esc не снимает блокировку PIN.", "item"),
        ("1 / 2 / 3 / 4 — вкладки Дом / Задачи / Холст / Статы (на главном экране, не в TextField).", "item"),
        ("Пробел — открыть Фокус-таймер (на главном экране, не в TextField).", "item"),
        ("На web Ctrl+N / Ctrl+F часто перехватывает браузер (новое окно / поиск по странице) — сочетание может не дойти до приложения.", "muted"),
        ("Сочетания не срабатывают, пока фокус в поле ввода (TextField).", "muted"),
        ("", "gap"),
        ("Жесты и действия", "head"),
        ("• Долгое нажатие на карточку задачи — закрепить / открепить", "item"),
        ("• Иконка булавки на карточке или в деталях — закрепить", "item"),
        ("• Оранжевая кнопка «+» — создать задачу или цель", "item"),
                        ("• Чипы на Доме — Брифинг / Итог / Завтра / Фокус; «ещё» — напоминания", "item"),
        ("• «↩ Отменить» после «Готово» — вернуть задачу", "item"),
        ("• «Отменить» в snack после лога прогресса — откат 30 с", "item"),
        ("• На Фокусе: чипы пресетов 15/5 и 50/10", "item"),
        ("• Крестик у напоминания бэкапа — скрыть на сегодня", "item"),
    ]

    def show_hotkeys(_e=None):
        rows: list[ft.Control] = []
        for line, kind in SHORTCUT_HELP_LINES:
            if kind == "gap":
                rows.append(ft.Container(height=6))
                continue
            if kind == "muted":
                rows.append(ft.Text(line, size=12, color=MUTED))
            elif kind == "head":
                rows.append(
                    ft.Text(line, size=13, weight=ft.FontWeight.W_700, color=TEXT)
                )
            else:
                rows.append(ft.Text(line, size=12, color=TEXT))
        show_info(
            page,
            title="Горячие клавиши",
            content=ft.Container(
                content=ft.Column(rows, spacing=6, tight=True, scroll=ft.ScrollMode.AUTO),
                width=320,
                height=300,
            ),
            ok_label="Закрыть",
        )


    archived_host = ft.Column(spacing=8)

    def _reload_archived():
        archived_host.controls.clear()
        with get_session() as session:
            archived = goal_service.list_goals(session, archived=True)
        if not archived:
            archived_host.controls.append(empty_state("Нет архивных целей", "Архив пуст", emoji="📦"))
        else:
            for g in archived:
                def _restore(e, gid=g.id, title=g.title):
                    with get_session() as session:
                        goal_service.unarchive_goal(session, gid)
                    show_snack(page, f"Восстановлено: {title}")
                    _reload_archived()
                    refresh_all()
                    page.update()

                archived_host.controls.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Text(g.title, size=13, color=TEXT, expand=True),
                                ft.TextButton("Восстановить", on_click=_restore),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=ft.Padding.symmetric(horizontal=4, vertical=2),
                    )
                )
        try:
            page.update()
        except Exception:
            pass

    _reload_archived()

    return ft.Container(
        content=ft.Column(
            [
                screen_header(
                    "Настройки",
                    subtitle="Профиль, защита и данные",
                    leading=ft.IconButton(
                        icon=ft.Icons.ARROW_BACK_IOS_NEW,
                        icon_color=TEXT,
                        icon_size=18,
                        on_click=lambda e: on_back(),
                    ),
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            group_heading("Профиль и вид"),
                            name_field,
                            muted("Пресеты акцента"),
                            preset_chips,
                            ft.Row(
                                [accent_field, preview],
                                spacing=12,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            week_sw,
                            compact_sw,
                            haptics_sw,
                            muted(
                                "Акцент применяется сразу. Компактный режим — меньше отступы. "
                                "Тактильность — вибрация на телефоне и лёгкий отклик на desktop."
                            ),
                        ],
                        spacing=12,
                    ),
                    padding=16,
                    **card_style(),
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            group_heading("Задачи"),
                            archive_recur_sw,
                            muted("После спавна следующего повтора родитель уходит в архив."),
                            auto_complete_sw,
                            muted("Родитель станет «Готово», когда все пункты отмечены."),
                        ],
                        spacing=10,
                    ),
                    padding=16,
                    **card_style(),
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            group_heading("Время и неделя"),
                            muted("Помодоро по умолчанию"),
                            ft.Row([work_field, break_field], spacing=10),
                            muted("Тихие часы — баннеры на Доме скрыты (по умолчанию 22→8)."),
                            ft.Row([quiet_start_f, quiet_end_f], spacing=10),
                            muted("Вечерний режим (карточка на Доме, с часа)."),
                            ft.Row([wind_down_f], spacing=10),
                            muted("Недельная цель задач (пн–вс)."),
                            ft.Row([weekly_target_f], spacing=10),
                        ],
                        spacing=10,
                    ),
                    padding=16,
                    **card_style(),
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            group_heading("Защита"),
                            muted("PIN — солёный хеш. 5 ошибок → пауза 30 с."),
                            lock_sw,
                            muted("При включении PIN спрашивается при запуске."),
                            change_pin_btn,
                            bio_sw,
                            muted(
                                lock_service.biometrics_unavailable_message()
                                if not lock_service.is_biometrics_available()
                                else "Face ID разблокирует приложение на этом устройстве."
                            ),
                        ],
                        spacing=10,
                    ),
                    padding=16,
                    **card_style(),
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            group_heading("Заморозка серии"),
                            muted(
                                "Раз в неделю один пропуск квоты не рвёт текущую серию "
                                "(meta: streak_freeze_used_week)."
                            ),
                            freeze_status,
                            freeze_btn,
                        ],
                        spacing=10,
                    ),
                    padding=16,
                    **card_style(),
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            group_heading("Резервная копия"),
                            muted(
                                "Экспорт и импорт JSON. FilePicker при доступности; "
                                "иначе путь в data/."
                            ),
                            pick_row,
                            ft.Container(
                                content=ft.Row(
                                    [
                                        ft.Icon(
                                            ft.Icons.FILE_DOWNLOAD_OUTLINED,
                                            color="#0F0F12",
                                            size=18,
                                        ),
                                        ft.Text(
                                            "Экспорт JSON",
                                            size=14,
                                            weight=ft.FontWeight.W_700,
                                            color="#0F0F12",
                                        ),
                                    ],
                                    alignment=ft.MainAxisAlignment.CENTER,
                                    spacing=8,
                                ),
                                bgcolor=ORANGE,
                                padding=14,
                                border_radius=ft.BorderRadius.all(14),
                                on_click=on_export_click,
                                ink=True,
                            ),
                            ft.Container(
                                content=ft.Row(
                                    [
                                        ft.Icon(
                                            ft.Icons.TABLE_CHART_OUTLINED,
                                            color=TEXT,
                                            size=18,
                                        ),
                                        ft.Text(
                                            "Экспорт CSV (задачи)",
                                            size=14,
                                            weight=ft.FontWeight.W_700,
                                            color=TEXT,
                                        ),
                                    ],
                                    alignment=ft.MainAxisAlignment.CENTER,
                                    spacing=8,
                                ),
                                bgcolor="#1C1C22",
                                padding=14,
                                border=ft.Border.all(1, BORDER),
                                border_radius=ft.BorderRadius.all(14),
                                on_click=do_export_csv,
                                ink=True,
                            ),
                            export_info,
                            import_path,
                            ft.Container(
                                content=ft.Row(
                                    [
                                        ft.Icon(
                                            ft.Icons.FILE_UPLOAD_OUTLINED,
                                            color=TEXT,
                                            size=18,
                                        ),
                                        ft.Text(
                                            "Импорт",
                                            size=14,
                                            weight=ft.FontWeight.W_700,
                                            color=TEXT,
                                        ),
                                    ],
                                    alignment=ft.MainAxisAlignment.CENTER,
                                    spacing=8,
                                ),
                                bgcolor="#1C1C22",
                                padding=14,
                                border_radius=ft.BorderRadius.all(14),
                                border=ft.Border.all(1, BORDER),
                                on_click=on_import_click,
                                ink=True,
                            ),
                            muted(
                                "По умолчанию: replace в пустую БД, иначе merge. "
                                "Replace создаёт снимок для отмены."
                            ),
                            import_info,
                            undo_btn_host,
                            undo_info,
                        ],
                        spacing=10,
                    ),
                    padding=16,
                    **card_style(),
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            group_heading("Архив целей"),
                            muted("Скрыты с Дома и квот — можно восстановить"),
                            archived_host,
                        ],
                        spacing=10,
                    ),
                    padding=16,
                    **card_style(),
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            group_heading("Онбординг"),
                            muted("Сбросить флаг и показать 3 карточки"),
                            ft.Container(
                                content=ft.Row(
                                    [
                                        ft.Icon(
                                            ft.Icons.SCHOOL_OUTLINED,
                                            color=TEXT,
                                            size=18,
                                        ),
                                        ft.Text(
                                            "Показать онбординг снова",
                                            size=14,
                                            weight=ft.FontWeight.W_700,
                                            color=TEXT,
                                        ),
                                    ],
                                    alignment=ft.MainAxisAlignment.CENTER,
                                    spacing=8,
                                ),
                                bgcolor="#1C1C22",
                                padding=14,
                                border_radius=ft.BorderRadius.all(14),
                                border=ft.Border.all(1, BORDER),
                                on_click=replay_onboarding,
                                ink=True,
                            ),
                        ],
                        spacing=10,
                    ),
                    padding=16,
                    **card_style(),
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            group_heading("Dev / сброс"),
                            muted(
                                "Для тестов: сброс celebration-флагов целей "
                                "(celebrated_goal_*)"
                            ),
                            ft.Container(
                                content=ft.Row(
                                    [
                                        ft.Icon(
                                            ft.Icons.RESTART_ALT,
                                            color=TEXT,
                                            size=18,
                                        ),
                                        ft.Text(
                                            "Сбросить celebration-флаги",
                                            size=14,
                                            weight=ft.FontWeight.W_700,
                                            color=TEXT,
                                        ),
                                    ],
                                    alignment=ft.MainAxisAlignment.CENTER,
                                    spacing=8,
                                ),
                                bgcolor="#1C1C22",
                                padding=14,
                                border_radius=ft.BorderRadius.all(14),
                                border=ft.Border.all(1, BORDER),
                                on_click=clear_celebrations,
                                ink=True,
                            ),
                        ],
                        spacing=10,
                    ),
                    padding=16,
                    **card_style(),
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            group_heading("Горячие клавиши"),
                            muted("Жесты и действия интерфейса (RU)"),
                            ft.Container(
                                content=ft.Row(
                                    [
                                        ft.Icon(
                                            ft.Icons.KEYBOARD_ALT_OUTLINED,
                                            color=TEXT,
                                            size=18,
                                        ),
                                        ft.Text(
                                            "Показать жесты и подсказки",
                                            size=14,
                                            weight=ft.FontWeight.W_700,
                                            color=TEXT,
                                        ),
                                    ],
                                    alignment=ft.MainAxisAlignment.CENTER,
                                    spacing=8,
                                ),
                                bgcolor="#1C1C22",
                                padding=14,
                                border_radius=ft.BorderRadius.all(14),
                                border=ft.Border.all(1, BORDER),
                                on_click=show_hotkeys,
                                ink=True,
                            ),
                        ],
                        spacing=10,
                    ),
                    padding=16,
                    **card_style(),
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            group_heading("О приложении"),
                            ft.Text(
                                f"TaskTimer {APP_VERSION} schema {SCHEMA_VERSION}",
                                size=14,
                                weight=ft.FontWeight.W_600,
                                color=TEXT,
                            ),
                            muted(
                                f"{FEATURE_COUNT} фичи · волны A–AU / A–AV · "
                                f"схема SQLite {SCHEMA_VERSION}"
                            ),
                            muted(
                                "Холст: бесконечная доска + Markdown-vault (data/notes/*.md)."
                            ),
                            muted(str(_readme_path())),
                            ft.Container(
                                content=ft.Row(
                                    [
                                        ft.Icon(
                                            ft.Icons.MENU_BOOK_OUTLINED,
                                            color=TEXT,
                                            size=18,
                                        ),
                                        ft.Text(
                                            "Открыть README",
                                            size=14,
                                            weight=ft.FontWeight.W_700,
                                            color=TEXT,
                                        ),
                                    ],
                                    alignment=ft.MainAxisAlignment.CENTER,
                                    spacing=8,
                                ),
                                bgcolor="#1C1C22",
                                padding=14,
                                border_radius=ft.BorderRadius.all(14),
                                border=ft.Border.all(1, BORDER),
                                on_click=show_readme,
                                ink=True,
                            ),
                        ],
                        spacing=10,
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
                ft.Container(height=8),
            ],
            spacing=14,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        ),
        padding=screen_insets(),
        expand=True,
    )
