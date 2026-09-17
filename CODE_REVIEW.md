# Code review — TaskTimer (schema 13 / Wave AQ)

Краткий отчёт по полному проходу: архитектура, сервисы, UI, vault, холст, smoke.

## Вердикт

Приложение в целом собрано хорошо: `main` уже корректно вяжет `build_canvas_board` + `on_open_note` → `note_editor`, вкладка «Холст», иконки заметок на Дом/Задачи/Фокус/Аналитика, schema 13 (`canvas_nodes` / `canvas_edges`), `SMOKE_OK`.

Найдены и исправлены реальные дефекты (ниже). Крупный рефакторинг не делался.

## Что было не так → что сделано

### Высокий / средний приоритет

| Проблема | Фикс |
|----------|------|
| **Path escape в vault** — проверка `str(path).startswith(str(root))` пропускает соседние пути вроде `…/notes_evil/…` | В `notes_service._resolve` — только flat-файл: `path.parent == root` и `is_relative_to(root)` |
| **Грязный `ref` у узлов холста** — `CanvasNodeCreate(ref="../../evil.md")` сохранял путь как есть | Санитизация в Pydantic (`CanvasNodeCreate` / `Update`) + `_safe_ref` в `canvas_service.create_node` / `update_node` |
| **Save в note_editor вызывал `refresh_all()`** — полный remount оверлея, сброс режима «Правка» и курсора | После сохранения только локальный `paint()` |
| **`lint_imports` не покрывал vault/canvas** — `notes_service`, `canvas_service`, `canvas_board`, `note_editor` отсутствовали | Добавлены в `scripts/lint_imports.py` (37 модулей) |
| **Ошибки seed vault/canvas глотались молча** в `init_db` | Пишем warning в stderr вместо голого `pass` |

### Низкий / UX

| Проблема | Фикс |
|----------|------|
| Онбординг всё ещё про «Роадмап», хотя nav — «Холст» | 3-я карточка: «Холст и заметки» |
| Карточки секций на холсте могли визуально подрезать текст | Высота seed `h=88`, padding карточки чуть плотнее |
| Esc закрывал `note`, но smoke Wave AD это не проверял | `note` в `_OVERLAY_SCREENS` + asserts Wave AD/AQ |
| Неиспользуемые: `CanvasNodeUpdate` import, `title_label` | Убраны |

### Подтверждено «уже ок» (гипотезы)

- `Switch label_style` — **нет** в коде; Flet 0.86 принимает `label` / `label_text_style` / `active_color`.
- Wiring `main` → canvas / note / иконки MD — на месте.
- Миграция schema 13: `Base.metadata.create_all` + индексы `canvas_*`.
- `sanitize_filename` режет traversal до basename; resolve дополнительно жёстко держит vault.
- Пустой vault / отсутствующий starter `.md` — `ensure_vault` / `list_notes` пересоздают стартеры; чужой missing-файл → `read_note` возвращает `""`.

## Файлы изменены

- `app/services/notes_service.py` — confinement
- `app/services/canvas_service.py` — `_safe_ref`, высота секций
- `app/schemas.py` — validators `ref`
- `app/ui/screens/note_editor.py` — save без remount
- `app/ui/screens/canvas_board.py` — import / padding / default h
- `app/ui/screens/onboarding.py` — карточка Холст
- `app/db.py` — seed warning
- `scripts/lint_imports.py`, `scripts/smoke_test.py` — покрытие
- `CODE_REVIEW.md` (этот файл)
- `app/services/export_service.py` — vault/canvas в export/import v2
- `app/main.py` — Esc → reminders
- `app/ui/screens/canvas_board.py` — IV framing
- `app/ui/screens/roadmap.py` — DEPRECATED
- Dist: `/workspace/TaskTimer-dist.zip`

## Nits закрыты (AQ+)

1. ~~Мёртвый `roadmap.py`~~ — DEPRECATED docstring; продукт = Холст + RM-слой.
2. ~~Экспорт без vault/canvas~~ — JSON v2: `notes` + `canvas_nodes`/`canvas_edges`; round-trip в smoke.
3. ~~Esc не закрывал reminders~~ — в `_OVERLAY_SCREENS`; smoke обновлён.
4. ~~InteractiveViewer без framing~~ — `alignment=TOP_LEFT` + zoom 0.88 на первый open.
5. `except Exception: pass` в Home/Settings — по-прежнему (не трогали массово); init/seed пишет warning в stderr.
6. ~~Dist `.flet`~~ — zip исключает `.venv`, `__pycache__`, `*.db`, `app/.flet/`, `.git`.

## Как проверить

```bash
cd /workspace/TaskTimer
.venv/bin/python scripts/smoke_test.py   # → SMOKE_OK
.venv/bin/python scripts/lint_imports.py # → LINT_IMPORTS_OK 37
.venv/bin/python -c "from app.services import notes_service; print(notes_service._resolve('home.md'))"
```

Ручной smoke (если открываете GUI): Настройки (Switch), вкладка Холст → тап по «Дом» → note editor → Esc назад; иконка MD на Доме.
