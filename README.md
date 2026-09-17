# TaskTimer

Премиальный тёмный таск-менеджер в стиле iPhone (viewport ~390×844) на **Python + Flet**.

Цвета: charcoal `#0F0F12`, акцент `#FF8A00` (пресеты + hex, применяется **на лету**).

## Стек

- Python 3.11+
- Flet (+ flet-charts)
- SQLAlchemy 2.x + SQLite
- Pydantic v2

## Возможности (Waves A–AS)

1. CRUD задач (статус / приоритет / срок / метка / связь с целью / **архив**)
2. **Повторяющиеся задачи** — `recur_rule` none|daily|weekly + `recur_anchor`; при «Готово» спавнится новая todo со сдвинутым сроком, пометкой «из повтора» и **копией открытых подзадач**; опция `archive_on_recur_done` архивирует родителя
3. **Чек-лист подзадач** — добавление / toggle / удаление с **confirm** / **↑↓ порядок**, cascade; чип прогресса на карточке
4. Детали задачи: все поля, DatePicker, повтор, архив
5. Цели с дневной квотой, ProgressLog, шаблоны; **архив целей** (скрыты с Дома)
6. Экран «Сегодня» — квоты: оставшееся, %, 🔥 streak, `+квота` / `+ лог`
7. **Серии (streaks)** и **календарь квоты** на цели
8. **Heatmap** активности (12–16 недель)
9. Фокус-таймер (Pomodoro) — дефолты из Настроек + **статы за 7 дней**
10. Roadmap: узлы, статусы, рёбра + **список связей from→to с удалением (confirm)**
11. Аналитика: donut + 14 дней + серии + heatmap + **фокус за неделю**
12. Фильтры задач: статус / **Сегодня** / Просрочено / **Архив** + чипы приоритета **Все / Высокий / Средний / Низкий**
13. Баннеры на Доме: просроченные и на сегодня → фильтр Задач
13a. **Глобальный поиск** (Дом / Задачи) — задачи + цели по названию
13b. Сортировка задач: умная / срок / приоритет / создано
13c. Описание / заметки multiline + markdown-lite (`**жирный**`)
14. Напоминания (колокольчик): due today / overdue / незакрытые квоты
15. Настройки: имя, accent, помодоро, **архив после повтора**, экспорт/импорт/отмена, **архив целей**, **«Показать онбординг снова»**
16. Seed один раз (`app_meta.seeded`); русский UI
17. **Wave I — онбординг** (BottomSheet, 3 RU-карточки: цели/квота, таймер, роадмап; Skip/Далее → `app_meta.onboarded`)
18. **Wave I — целостность целей**: `goal.current_value` всегда пересчитывается из ProgressLog после CRUD/импорта; `repair_all_goal_values` при старте
19. Confirm на деструктивные действия (задачи, цели, логи, узлы, подзадачи, replace-импорт)
20. **Wave J — онбординг снова**: Settings сбрасывает `onboarded`, sheet сразу / на следующем Доме; акцент на карточках
21. **Wave J — multi-select задач**: чекбоксы на карточках + «В архив» пачкой
22. **Wave K — закрепление задач**: `tasks.pinned`; закреплённые сверху на Доме/Задачах; toggle на карточке и в деталях
23. **Wave K — история фокуса**: последние 20 TimeSessions (длительность / статус / метка) на экране Фокус
24. **Wave K — недельная полоска**: 7 точек активности под heatmap на Доме
25. **Wave L — дублирование задачи**: кнопка на деталях клонирует title/desc/priority/goal/открытые подзадачи/recur/color → status todo
26. **Wave L — фильтр меток**: чипы `color_tag` на экране Задач (+ «Закреплённые»)
27. **Wave L — snackbars**: после duplicate / pin / batch archive
28. **Wave M — относительные сроки**: вчера / сегодня / завтра / через N дн на карточках
29. **Wave M — неделя на Доме**: блок «На этой неделе» по `week_due_summary`
30. **Wave M — bulk Готово / очистка**: пакетное завершение + «Очистить выполненные → архив»

31. **Wave N — прогноз цели**: дней до завершения по `daily_quota` vs остаток на деталях цели
32. **Wave N — тихие часы**: `app_meta.quiet_start`/`quiet_end` (22/8); баннеры напоминаний на Доме скрыты, счётчик просрочек приглушён
33. **Wave N — empty illustrations**: emoji/icon empty states вместо «голого» muted

34. **Wave O — прогноз на Статах**: секция «Прогноз целей» с `days_to_complete`
35. **Wave O — последний экспорт**: путь/время в `app_meta` после экспорта, показ в Настройках
36. **Wave O — совет дня**: 5 RU-tips под шапкой Дома, индекс в meta раз в сутки


37. **Wave P — шаблоны задач**: чипы «Срочное» / «Обычное» / «Повтор daily» на Создать (режим задачи) → priority/recur
38. **Wave P — авто-раскладка карты**: кнопка BFS-уровней по рёбрам → сетка x/y с сохранением позиций

39. **Wave Q — устойчивость UI**: защита от AttributeError на Доме; quiet/tips без битой meta; шаблоны в режиме цели на Создать
40. **Wave R — оценка времени**: `tasks.estimated_min`; поле «Оценка, мин»; чип `⏱ Nм`; «Оценка на сегодня» на Доме
41. **Wave R — snooze срока**: кнопки «+1 день» / «+7 дней» на детали задачи
42. **Wave R — авто-готово по подзадачам**: настройка «Завершать задачу, когда все подзадачи готовы»
43. **Wave R — обзор недели**: секция на Аналитике (завершено / фокус / квоты / серия)
44. **Wave R — celebration snack**: при 100% цели после лога — один раз (`celebrated_goal_{id}`)
45. **Wave R — квоты polish**: «✓ Квота закрыта» + усиленный остаток на карточке сегодня
46. **Wave T — импульс/застой**: momentum score + блок «Застой» на Доме
47. **Wave S — релиз-гигиена**: `CHANGELOG.md` (RU A–R), README/feature_matrix, чистый dist, `install.ps1`, двойной smoke
48. **Wave U — итог дня**: кнопка «Итог дня» на Доме (квоты / задачи готово / фокус мин / совет на завтра); сброс celebration-флагов в Настройках (Dev)
49. **Wave V — умный совет**: карточка на Доме (застой → лог / просрочка → Задачи / незакрытая квота); скрыть на сегодня; snack экспорта с числом и размером
50. **Wave W — пресеты фокуса / badge**: чипы 15/5 и 50/10 на Фокусе (settings); badge активных на «Задачи»; harden dismiss умного совета
51. **Wave X — inbox / заметка / undo / CSV / compact**: быстрый захват → inbox; «Входящие»; заметка дня; ↩ Отменить Готово; CSV; undo лога 30с; compact_ui
52. **Wave Y — недавний поиск / сорт целей**: `recent_searches` JSON в meta (5); чипы в поиске; Дом — цели по % desc
53. **Wave Z — About**: в Настройках версия / schema 11 / счётчик фич / путь README
54. **Wave AA — горячие клавиши**: лист жестов из Настроек «Горячие клавиши» (RU)
55. **Wave AA — напоминание бэкапа**: на Доме muted «Сделайте экспорт бэкапа», если `last_export_at` старше 7 дней или отсутствует
56. **Wave AB — Ctrl+N**: `page.on_keyboard_event` → экран создания (desktop); на web браузер часто перехватывает Ctrl+N
57. **Wave AB — dismiss бэкап-tip**: скрыть напоминание бэкапа на сегодня (`backup_tip_dismissed` в meta)
58. **Wave AC — Ctrl+F**: `page.on_keyboard_event` → оверлей поиска (desktop); игнор, пока фокус в TextField; на web браузер часто перехватывает Ctrl+F
59. **Wave AD — Esc**: закрывает оверлеи search/create/settings/focus/detail, если не в TextField (`leave_overlay` из main)
60. **Wave AE — 1/2/3/4**: на main переключают вкладки Дом/Задачи/Карта/Статы (0-based), не в TextField
61. **Wave AF — Пробел**: на main открывает Фокус-таймер, не в TextField
62. **Wave AG — утренний брифинг**: кнопка «Брифинг» на Доме — просрочено / на сегодня / открытые квоты / импульс / один совет
63. **Wave AH — вечерний режим**: с `wind_down_hour` (по умолчанию 18) мягкая карточка «Вечерний режим» на Доме — незакрытые квоты + ссылка на итог дня (не блок)
64. **Wave AI — план на завтра**: кнопка «Завтра» на Доме — задачи со сроком на завтра, открытые сегодня + подсказка
65. **Wave AJ — недельная цель**: target completed tasks/ISO week (default 10); Home/Analytics bar «Неделя: X/Y задач»; meta `weekly_task_target`
66. **Wave AK — отложить просроченные**: кнопка «+1д» на баннере просрочки на Доме — `snooze_all_overdue` на все overdue
67. **Wave AL — заморозка серии**: раз в ISO-неделю «Заморозить серию» (Настройки) → meta `streak_freeze_used_week`; текущая серия переживает 1 gap
68. **Wave AM — заметка сессии фокуса**: колонка `time_sessions.note` (schema **12**); TextField на Фокусе + сохранение при «Готово» / автозавершении
69. **Wave AN — фильтр истории фокуса**: чипы **Все / С заметкой** на списке истории; полный текст заметки под строкой
70. **Wave AO — заметки фокуса в аналитике**: секция последних 5 завершённых сессий с заметкой (title + snippet)
71. **Wave AP — тап заметки → Фокус**: в Аналитике тап по snippet открывает экран Фокуса (`on_open_focus`); иначе копирует в буфер
72. **Wave AQ — Холст + Markdown vault**: бесконечный pan/zoom холст (вкладка «Холст»), секции = `.md` файлы в `data/notes/`, редактор Preview/Edit (GFM), schema 13 (`canvas_nodes` / `canvas_edges`)
73. **Wave AR — PIN-лок и иконка**: первый запуск (splash → онбординг → настройка PIN / «Настроить позже»); повторный запуск с локом — экран PIN; солёный PBKDF2-хеш; Face ID-переключатель с fallback на desktop; `assets/icon.png`
74. **Wave AS — iOS IPA ready**: `pyproject.toml` / fullscreen iPhone layout / `icon_ios.png` / docs/IOS_BUILD.md; FEATURE_COUNT 74

## Быстрая установка (Windows)

```powershell
cd C:\Users\Admin\Desktop\Projects\TaskTimer
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

## Установка вручную

```powershell
cd C:\Users\Admin\Desktop\Projects\TaskTimer
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
```

## Запуск

```powershell
.\.venv\Scripts\Activate.ps1
flet run app/main.py
```

Альтернативы:

```powershell
python -m flet run app/main.py
python app/main.py
```

Иконка приложения: официальный бренд `assets/icon.png` (и `assets/icon-192.png`; окно — `page.window.icon`, Flet `assets_dir`). PIN хранится только как солёный хеш; блокировку можно включить в Настройках.

Web (если доступен Flet web):

```powershell
flet run app/main.py --web
```

## Smoke-тест

```powershell
.\.venv\Scripts\Activate.ps1
python scripts/smoke_test.py
```

Проверяет: seed, CRUD, подзадачи, streaks, heatmap, settings/pomodoro, export/import/soft undo, accent, таймер, roadmap, аналитику, архив задач, **recur + copy open subtasks**, **archive_on_recur_done**, **goal archive**, **weekly focus**, **priority filter**, reminders, due_today, **global search**, **task sort**, **markdown-lite**, **onboarding meta + replay**, **goal current_value integrity / repair**, **batch archive**, **roadmap edge titles/delete**, **pin sort/toggle**, **focus history 20**, **focus history note filter**, **week strip**, **duplicate task**, **color_tag chips**, **schema 10**, **goal forecast**, **quiet hours**, **empty illus**, **analytics ETA list**, **last export meta**, **home daily tips**, **task templates**, **roadmap auto-layout**, **estimated_min / today estimate**, **snooze_due**, **auto_complete_subtasks**, **weekly review**, **celebration snack**, **smart suggestion**, **export snack summary**, **morning briefing**, **tomorrow plan**, **snooze all overdue**.

## Экраны

| Экран | Описание |
|-------|----------|
| **Онбординг** | Первый запуск: splash → 3 карточки (цели, таймер, холст) → настройка PIN |
| **Блокировка** | Полный экран PIN (4 точки, цифровая клавиатура, Face ID fallback) |
| **Дом** | Прогресс, **совет дня**, **умный совет**, **Брифинг**, **Завтра**, **Вечерний режим**, **напоминание бэкапа** (7д, dismiss сегодня), квоты/рекорд, **оценка на сегодня**, баннеры, напоминания, **поиск**, серии, heatmap + **неделя (7 точек)**, цели, **закреплённые** задачи, ⚙, Фокус |
| **Задачи** | Статус / Сегодня / Просрочено / Архив + приоритет + **метки (color_tag)** + **сортировка** + **pin** + глобальный поиск + **multi-select → В архив** |
| **+ Создать** | Задача (шаблоны priority/recur + повтор) или цель (шаблоны) |
| **Карта** | Canvas + узлы/рёбра + список связей + **авто-раскладка** |
| **Статы** | Donut + серии + heatmap + 14 дней + **фокус 7д** + **заметки фокуса (5)** + **прогноз целей** + **Обзор недели** |
| **Фокус** | Pomodoro + недельные итоги + **история 20** + чипы **Все / С заметкой** |
| **Настройки** | Имя, акцент, помодоро, **тихие часы**, архив после повтора, **авто-готово по подзадачам**, **PIN / Face ID**, экспорт JSON/**CSV**, **архив целей**, **онбординг снова**, **Горячие клавиши**, **О приложении** |
| **Напоминания** | Due today / overdue / квоты |
| **Поиск** | Глобальный overlay: задачи + цели по названию → детали |
| **Детали** | Задача (чек-лист ↑↓, **оценка мин**, **snooze +1/+7**, повтор, **pin**, **дублировать**, архив) / Цель (календарь, **прогноз дней**, архив) |

## База данных

SQLite: `data/tasktimer.db` (создаётся автоматически).

Версия схемы: `SCHEMA_VERSION = 13` в `app_meta`.

- **v13 + Wave AS**: iOS packaging (`pyproject.toml`, fullscreen mobile, `icon_ios.png`, IOS_BUILD.md); FEATURE_COUNT 74; schema 13 без бампа
- **v13 + Wave AR**: PIN-лок (PBKDF2), splash / setup / lock screens, `assets/icon.png`; FEATURE_COUNT 73; schema 13 без бампа
- **v13 + Wave AQ**: Infinite canvas tab «Холст»; MD vault `data/notes/`; note editor GFM; canvas_nodes/edges; FEATURE_COUNT 72; schema 12→13
- **v12 + Wave AP**: Analytics focus-note tap → Focus (`on_open_focus`); clipboard fallback; FEATURE_COUNT 71; schema 12 без бампа
- **v12 + Wave AO**: Analytics «Заметки фокуса» last 5 completed sessions with notes; FEATURE_COUNT 70; schema 12 без бампа
- **v12 + Wave AN**: Focus history chips Все / С заметкой; note text under history rows; FEATURE_COUNT 69; schema 12 без бампа
- **v12 + Wave AM**: Focus session notes (`time_sessions.note`); TextField + save on complete; FEATURE_COUNT 68; schema bump 11→12
- **v11 + Wave AL**: Settings streak freeze once/ISO week (`streak_freeze_used_week`); current streak skips 1 gap; FEATURE_COUNT 67; no schema bump
- **v11 + Wave AK**: Home overdue banner «+1д» batch snooze via `snooze_all_overdue`; FEATURE_COUNT 66; no schema bump
- **v11 + Wave AJ**: Home/Analytics weekly goal bar «Неделя: X/Y задач»; `weekly_task_target` meta (default 10); `count_completed_iso_week` / `weekly_goal_progress`; FEATURE_COUNT 65; no schema bump
- **v11 + Wave AI**: Home «Завтра» dialog (due tomorrow + open today carry + tip); `tomorrow_plan` / `is_due_tomorrow`; FEATURE_COUNT 64; no schema bump
- **v11 + Wave AH**: Home soft «Вечерний режим» card when hour ≥ wind_down_hour (default 18); incomplete quotas + link to daily wrap; Settings editable; FEATURE_COUNT 63; no schema bump
- **v11 + Wave AG**: Home «Брифинг» dialog (overdue / due today / open quotas / momentum / one suggestion); FEATURE_COUNT 62; no schema bump
- **v11 + Wave AF**: Space → Focus timer on main; ignored in TextField; FEATURE_COUNT 61; no schema bump
- **v11 + Wave AE**: digits 1–4 → bottom tabs on main (Home/Tasks/Map/Stats); ignored in TextField; FEATURE_COUNT 60; no schema bump
- **v11 + Wave AD**: Esc → leave overlay (search/create/settings/focus/detail) when not in TextField; FEATURE_COUNT 59; no schema bump
- **v11 + Wave AC**: Ctrl+F → search (desktop `on_keyboard_event`; ignored while TextField focused; web may be blocked by browser); FEATURE_COUNT 58; no schema bump
- **v11 + Wave AB**: Ctrl+N → create (desktop `on_keyboard_event`; web may be blocked by browser); Home backup tip dismiss today (`backup_tip_dismissed`); FEATURE_COUNT 57; no schema bump
- **v11 + Wave AA**: Settings «Горячие клавиши» gesture sheet (RU); Home backup tip if last_export_at ≥7d/missing; FEATURE_COUNT 55; no schema bump
- **v11 + Wave Z**: Settings About (`TaskTimer 1.0 schema 11`, feature count, README path); no schema bump
- **v11 + Wave Y**: recent_searches JSON chips; Home goals sort percent desc
- **v11 + Wave X**: `tasks.inbox`; quick capture; daily note; undo complete; «Входящие»; CSV; undo progress-log snack; compact_ui
- **v10 + Wave V**: Home smart suggestion (stuck/overdue/quota), dismiss today; export size/count snack
- **v10 + Wave U**: Home «Итог дня» (quotas/tasks/focus/tip); Settings clear celebrated flags
- **v10 + Wave T**: momentum score + stuck goals on Home
- **v10 + Wave S**: CHANGELOG.md (RU A–R); README/feature_matrix; clean dist zip; install.ps1; double smoke
- **v10 + Wave R**: `estimated_min`; snooze due; `auto_complete_subtasks`; Analytics «Обзор недели»; celebration snack; habit quota polish
- **v9 + Wave P**: Create task template chips (Срочное/Обычное/Повтор daily); roadmap auto-layout BFS grid
- **v9 + Wave O**: Analytics «Прогноз целей»; last_export_path/at in app_meta; Home daily tip (5 RU, meta index)
- **v9 + Wave N**: goal days-to-complete forecast; quiet_start/quiet_end (22/8); Home reminder banners suppressed in quiet window; emoji empty states
- **v9 + Wave M**: relative due labels; home week-due banner; batch complete + clear-done archive; pinned filter chip
- **v9 + Wave L**: duplicate task (open subtasks); color_tag chip filter on Tasks; snackbars after duplicate/pin/batch archive; long-press pin (no schema bump)
- **v9 + Wave K**: `tasks.pinned` + index; pin-first sort on Home/Tasks; pin toggle on card/detail; Focus history last 20; Home 7-day activity dots under heatmap; export/import pinned
- **v8 + Wave J**: replay onboarding from Settings; roadmap edge list + delete confirm; task multi-select batch archive; onboarding uses live accent
- **v8 + Wave I**: `app_meta.onboarded`, first-run BottomSheet; `repair_all_goal_values` / recalc after log CRUD & import; subtask delete confirm
- **v8**: recurring tasks (`recur_rule`/`recur_anchor`), copy open subtasks on spawn, `archive_on_recur_done`, goal soft-archive, priority/focus indexes, weekly focus stats UI; Wave H: global search, task sort, notes markdown-lite, Home query tidy
- **v7**: архив задач, индексы SQLite, in-app reminders, goal templates.
- **v6**: pomodoro defaults в settings (`pomodoro_work_min`/`pomodoro_break_min`), фильтр «Сегодня», polish квот/empty states, accent presets, FilePicker, soft undo.
- **v5**: import/export round-trip, live accent, streak calendar, subtask reorder.
- **v4**: `subtasks` + ключи настроек.

Экспорт / импорт: `data/export-YYYYMMDD-HHMMSS.json` (или путь из FilePicker).

- **Импорт по умолчанию**: `replace` в пустую БД, иначе `merge` по названию.
- **Replace**: снимок `pre-import-*.json` → «Отменить импорт».
- После импорта `current_value` целей пересчитывается из логов.

## Структура

```
TaskTimer/
  requirements.txt
  README.md
  CHANGELOG.md
  install.ps1
  scripts/smoke_test.py
  scripts/feature_matrix.md
  app/
    main.py
    db.py
    models.py
    schemas.py
    services/
    ui/
      theme.py
      components/
      screens/   # + onboarding.py (Wave I)
```

## Сборка iOS IPA

Подробно: **[docs/IOS_BUILD.md](docs/IOS_BUILD.md)**.

- Bundle ID: `com.rom4ik121.tasktimer`
- На **реальном iPhone** UI на весь экран (без декоративной рамки 390×844); на desktop рамка-превью сохраняется
- IPA собирается **только на macOS + Xcode 15+** (`flet build ipa` / `flet build ios-simulator`) — не на Windows/Linux
- `SQLAlchemy==2.0.36` (iOS wheels); Face ID — Info.plist готов, PIN основной до плагина local_auth

```bash
flet build ios-simulator
flet build ipa --ios-team-id … --ios-export-method debugging
```

## Примечание

Не коммитьте `.venv/`, `__pycache__/`, `data/*.db` в дистрибутив.
