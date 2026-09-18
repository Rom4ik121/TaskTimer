# TaskTimer — журнал изменений

Кратко по волнам **A–AT** (схема SQLite → `SCHEMA_VERSION = 13`). Wave **AT** — UX-полировка Дома, тосты/модалки и валидация.

Исторические волны Z–AL: SCHEMA_VERSION = 11 (без бампа до AM).

## AT — UX polish: Дом, тосты, валидация

- Дом: фокус на приветствии, захват, задачи; дайджесты — чипы (Брифинг / Итог / Завтра / Фокус); сворачиваемый лист «Сегодня»
- Баннеры: максимум 2 сразу (`MAX_HOME_BANNERS`); остальные за «ещё» → Напоминания. Прогресс/heatmap остаются в Статах
- Общий API в `dialogs.py`: `show_toast` (success/error/info/warning + undo), `show_info`, `confirm_action` / `confirm_delete`, `validation_fail` + поле `error_text`
- Валидация RU: создать задачу/цель, настройки, PIN, заметка, холст — не молчит при пустых/неверных полях
- Шапки Задачи / Холст / Статы / Настройки; Настройки «Защита» и длинные списки — `group_heading` + меньше шума
- Адаптив: `screen_insets` / compact / wrap чипов; SafeArea Wave AS без изменений
- FEATURE_COUNT 75; schema 13 без бампа; smoke Wave AT

## AS — iOS IPA ready / iPhone layout

- `pyproject.toml`: product TaskTimer, org/bundle `com.rom4ik121.tasktimer`, splash `#0F0F12`, `SQLAlchemy==2.0.36`, entry `main.py` → `app.main:main`
- На iOS/Android: полноэкранный UI без декоративной «рамки телефона»; SafeArea; desktop-превью 390×844 сохранено
- `assets/icon_ios.png` ≥1024×1024 (opaque charcoal); `[tool.flet.ios.info]` NSFaceIDUsageDescription (RU)
- Face ID: preference + Info.plist; `try_biometric_unlock` (плагин later); PIN основной; desktop не врёт про Face ID
- flet-charts: опциональный import + fallback колец/графиков при отсутствии расширения
- Docs: `docs/IOS_BUILD.md` (RU); README секция iOS; **IPA только на macOS+Xcode**
- FEATURE_COUNT 74; schema 13 без бампа; smoke Wave AS + dist

## AR — PIN-лок, первый запуск, иконка

- Иконка `assets/icon.png` + `assets/icon-192.png` — официальный бренд (оранжевое кольцо-таймер с галочкой на charcoal squircle); `page.window.icon` + `ft.run(..., assets_dir=assets)`
- PIN из 4 цифр, только **солёный хеш** PBKDF2-HMAC-SHA256 в `app_meta` (`pin_salt` / `pin_hash`)
- Первый запуск: splash (~0.8 с, можно пропустить) → онбординг → «Защитите приложение» (PIN → повтор → Face ID) или «Настроить позже»
- Повторный запуск при включённой блокировке: полный экран «Введите PIN», iOS-клавиатура, Face ID (на desktop — «Face ID недоступен на этом устройстве — используйте PIN»)
- 5 неверных попыток → пауза 30 с; Esc **не** снимает блокировку
- Настройки: включить/выключить лок, сменить PIN, предпочтение биометрии
- FEATURE_COUNT 73; schema 13 без бампа; smoke Wave AR

## AQ+ — полировка code review (nits)

- Экспорт/импорт JSON v2: vault `notes` + `canvas_nodes` / `canvas_edges` (sanitize при импорте)
- Esc закрывает напоминания (как остальные оверлеи)
- `roadmap.py` помечен DEPRECATED — RM-слой на Холсте
- InteractiveViewer: `alignment=TOP_LEFT` + лёгкий zoom-out на первый open
- Dist zip без `.venv` / `__pycache__` / `*.db` / `app/.flet` / `.git`
- Онбординг/Настройки: копия про Холст + MD vault

## AQ — Холст + Markdown vault (schema 13)

- Вкладка **Холст** (вместо «Карта»): бесконечный pan/zoom (`InteractiveViewer`), тёмный оранжевый premium
- Vault `data/notes/*.md` — секции Дом/Задачи/Цели/Фокус/Аналитика/Роадмап + свободные заметки
- `notes_service` + экран `note_editor` (Preview GFM / Edit)
- Тап по узлу холста → открытие MD; иконки заметок в шапках экранов
- Таблицы `canvas_nodes`, `canvas_edges`; слой роадмапа опционально на холсте
- FEATURE_COUNT 72

## A–F — ядро
- **A**: задачи, цели, квоты, ProgressLog, тёмный UI (charcoal / accent).
- **B**: подзадачи, приоритеты, статусы, color_tag.
- **C**: фокус-таймер (Pomodoro) и TimeSession.
- **D**: роадмап — узлы, рёбра, статусы.
- **E**: аналитика — donut, 14 дней, heatmap, серии.
- **F**: настройки (имя, акцент, неделя с Пн), экспорт JSON.

## G–J — данные и UX
- **G**: импорт merge/replace + soft-undo снимка.
- **H**: глобальный поиск, сортировки задач, markdown-lite (`**жирный**`).
- **I**: онбординг (3 RU-карточки), целостность `goal.current_value` / repair при старте.
- **J**: повтор онбординга, пакетный архив задач, список связей роадмапа с удалением.

## K–N — продуктивность
- **K**: pin задач, история фокуса (20), полоска недели на Доме; schema pin.
- **L**: дубликат задачи, фильтр меток, snackbars.
- **M**: относительные сроки, сводка «на этой неделе», bulk Готово / очистка done.
- **N**: прогноз дней до цели, тихие часы, empty-state с emoji.

## O–R — полировка и schema 10
- **O**: прогноз целей в аналитике, мета последнего экспорта, совет дня на Доме.
- **P**: шаблоны задач (Срочное / Обычное / Повтор daily), авто-раскладка роадмапа.
- **Q**: защита AttributeError на Доме, quiet/tips без meta, шаблоны в режиме цели.
- **R**: `estimated_min` + оценка на сегодня; snooze +1/+7; `auto_complete_subtasks`; «Обзор недели»; celebration 100%; polish квот.

## S — релиз-гигиена
- README + feature_matrix (A–S), `CHANGELOG.md`, чистый dist zip, `install.ps1`, двойной smoke → `SMOKE_OK`.

## T — импульс и застой
- **Momentum score** (0–100): `compute_momentum_score` / `momentum_score` — квоты сегодня % ×0.4 + completion задач ×0.4 + best streak (cap 14) ×0.2; мини-кольцо «Импульс» на Доме.
- **Застой**: цели без ProgressLog ≥3 дней и не завершённые — блок «Застой» на Доме.
- Smoke Wave T + обновлённый dist.

## U — итог дня
- **Итог дня** на Доме: кнопка открывает диалог — квоты закрыты, задач готово сегодня, фокус-минуты сегодня, совет на завтра (`daily_wrap` / `get_tomorrow_home_tip`).
- **Сбросить celebration-флаги** в Настройках (Dev / сброс) — `clear_celebrated_flags` удаляет `celebrated_goal_*` для повторного теста 🎉.
- Smoke Wave U + обновлённый dist.

## V — умный совет
- **Smart suggestion** на Доме: застой → лог; иначе просрочка → Задачи; иначе первая незакрытая квота. Одна фраза RU, скрыть на сегодня (`smart_suggest_dismissed`).
- **Экспорт**: JSON по-прежнему включает settings; после экспорта snack с числом задач/целей и размером файла.
- Smoke Wave V + обновлённый dist.

## W — пресеты фокуса и badge
- **Focus presets**: экран Фокус читает `pomodoro_work_min` / `pomodoro_break_min` из Настроек; быстрые чипы **15/5** и **50/10** (таймер + запись в settings).
- **Task count badge**: badge активных задач на вкладке «Задачи» в NavigationBar + чип «Задачи» в шапке Дома.
- **Smart suggest dismiss**: жёсткая обработка пустого/мусорного meta, ISO datetime, идемпотентный dismiss, `clear_smart_suggest_dismiss`.
- Smoke Wave W + обновлённый dist.

## X — inbox, заметка дня, undo, CSV, compact
- **Quick Capture / Inbox** (schema 11): колонка `tasks.inbox`; быстрый захват на Доме → todo medium в inbox; чип «Входящие» на Задачах; promote при полном редактировании / `set_inbox`.
- **Заметка дня**: ключ `daily_note_YYYY-MM-DD` в app_meta; карточка на Доме.
- **↩ Отменить Готово**: мета `last_completed_*`; чип на Доме после завершения задачи.
- **CSV экспорт**: `export_tasks_csv` + кнопка в Настройках рядом с JSON.
- **Undo last progress log**: snack «Отменить» 30 с после быстрого лога / `+квота` на Доме.
- **Compact mode**: настройка `compact_ui` — меньше padding у карточек на Доме.
- Smoke Wave X + dist zip.

## Y — недавний поиск и сортировка целей
- **Recent searches**: последние 5 запросов в `app_meta.recent_searches` (JSON); чипы «Недавние» в оверлее поиска (Enter / клик по результату / чип).
- **Goal sort**: на Доме цели по `%` убыв. (`list_goals(..., sort="percent")`); отдельного списка целей нет.
- Smoke Wave Y + обновлённый dist.

## Z — About и релиз дня
- **SCHEMA_VERSION**: сверено с колонками (`inbox` и пр.) — остаётся **11**, бамп не нужен; README / CHANGELOG / smoke согласованы.
- **О приложении** в Настройках: `TaskTimer 1.0 schema 11`, строка «53 фичи · волны A–Z», путь к README + кнопка «Открыть README».
- Двойной smoke → `SMOKE_OK`; чистый dist zip; `AFTERNOON_STATUS.md` (RU) для деплоя.

## AA — горячие клавиши и напоминание бэкапа
- **Горячие клавиши** в Настройках: лист жестов (RU) — long-press pin, булавка, «+», шапка Дома, undo Готово/лог, пресеты фокуса.
- **Напоминание бэкапа** на Доме: muted «Сделайте экспорт бэкапа», если `last_export_at` отсутствует или старше 7 дней (`export_service.needs_backup_reminder`); тап → Настройки.
- FEATURE_COUNT → 55; schema 11 без бампа; smoke Wave AA + dist.

## AB — Ctrl+N и dismiss бэкап-tip
- **Ctrl+N**: `page.on_keyboard_event` открывает экран создания (desktop / native). На **web** браузер часто перехватывает Ctrl+N (новое окно) — сочетание может не дойти; задокументировано в листе «Горячие клавиши».
- **Dismiss бэкап-tip**: крестик на Доме скрывает напоминание на сегодня (`app_meta.backup_tip_dismissed`, ISO date); аналогично smart suggest.
- FEATURE_COUNT → 57; schema 11 без бампа; smoke Wave AB + dist.

## AD — Esc закрывает оверлеи
- **Esc**: `page.on_keyboard_event` вызывает `leave_overlay` для search/create/settings/focus/detail (task/goal), если фокус не в TextField; callback из `main`.
- FEATURE_COUNT → 59; schema 11 без бампа; smoke Wave AD + dist.

## AE — цифры 1–4 переключают вкладки
- **1 / 2 / 3 / 4**: на главном экране (`screen == main`) переключают нижние вкладки Дом / Задачи / Карта / Статы (индексы 0–3), если фокус не в TextField; без Ctrl/Alt.
- Лист «Горячие клавиши» обновлён; FEATURE_COUNT → 60; schema 11 без бампа; smoke Wave AE + dist.

## AI — план на завтра
- **План на завтра** на Доме: кнопка «Завтра» → диалог — задачи со сроком на завтра, ещё открытые сегодня (хвост), подсказка RU.
- Сервис `analytics_service.tomorrow_plan` + `task_service.is_due_tomorrow`.
- FEATURE_COUNT → 64; schema 11 без бампа; smoke Wave AI + dist.

## AP — тап заметки фокуса → Фокус
- В Аналитике тап по строке «Заметки фокуса» открывает экран Фокуса через `on_open_focus` (как на Доме).
- Fallback: если колбэк не передан — копирует snippet в буфер + snack.
- FEATURE_COUNT → 71; schema 12 без бампа; smoke Wave AP + dist.

## AO — заметки фокуса в аналитике
- **Analytics focus notes**: секция «Заметки фокуса» — последние 5 завершённых сессий с непустой `note` (title/`label` + snippet).
- Сервис `analytics_service.recent_focus_notes` + схема `FocusNoteSnippet`.
- FEATURE_COUNT → 70; schema 12 без бампа; smoke Wave AO + dist.

## AN — фильтр истории фокуса
- **Focus history filter**: чипы **Все / С заметкой** на списке истории Фокуса; `list_sessions(..., has_note=True)`.
- Текст заметки целиком под строкой истории (`max_lines=4`), если `note` не пустой.
- FEATURE_COUNT → 69; schema 12 без бампа; smoke Wave AN + dist.

## AM — заметка сессии фокуса
- **Session notes**: колонка `time_sessions.note` (Text, default `''`); `SCHEMA_VERSION` **11→12** + migrate.
- Фокус: TextField «Заметка сессии»; кнопка ✓ / автозавершение таймера → `timer_service.complete(..., note=)`.
- Экспорт/импорт JSON сохраняет `note`; история показывает заметку.
- FEATURE_COUNT → 68; smoke Wave AM + dist.

## AL — заморозка серии
- **Заморозка серии**: раз в ISO-неделю (пн–вс) кнопка «Заморозить серию» в Настройках → meta `streak_freeze_used_week` (`YYYY-Www`).
- `streak_service._compute_streaks(..., allow_one_gap=True)`: один пропуск квоты не рвёт **текущую** серию (gap не увеличивает длину); **best** считает только реальные дни.
- Карточка «Заморозка серии» с пояснением RU.
- FEATURE_COUNT → 67; schema 11 без бампа; smoke Wave AL + dist.

## AK — отложить просроченные
- **+1д всем**: кнопка на баннере просрочки на Доме вызывает `task_service.snooze_all_overdue` (+1 день ко всем overdue).
- FEATURE_COUNT → 66; schema 11 без бампа; smoke Wave AK + dist.

## AJ — недельная цель задач
- **Недельная цель**: meta `weekly_task_target` (default 10, 1–200) в Настройках; прогресс-бар «Неделя: X/Y задач» на Доме и в Аналитике.
- Сервис `count_completed_iso_week` / `weekly_goal_progress` — считает `completed_at` за текущую ISO-неделю (пн–вс).
- FEATURE_COUNT → 65; schema 11 без бампа; smoke Wave AJ + dist.

## AH — вечерний режим
- **Вечерний режим** на Доме: если локальный час ≥ `wind_down_hour` (meta / Настройки, по умолчанию 18) — мягкая карточка «Вечерний режим» со счётчиком незакрытых квот и ссылкой на «Итог дня». Не блокирует работу.
- `is_wind_down` / `SettingsOut.wind_down_hour`; поле в Настройках рядом с тихими часами.
- FEATURE_COUNT → 63; schema 11 без бампа; smoke Wave AH + dist.

## AG — утренний брифинг
- **Брифинг** на Доме: кнопка рядом с «Итог дня» открывает диалог — просрочено, на сегодня, список незакрытых квот, импульс, один умный совет (RU).
- Сервис `morning_briefing(session)` собирает overdue / due_today / today_quotas / momentum_score / compute_smart_suggestion (dismiss на Доме не прячет совет в диалоге).
- FEATURE_COUNT → 62; schema 11 без бампа; smoke Wave AG + dist.

## AF — Пробел открывает Фокус
- **Пробел (Space)**: на главном экране (`screen == main`) открывает экран Фокус-таймера, если фокус не в TextField; без Ctrl/Alt. Повторно на Фокусе — no-op.
- Лист «Горячие клавиши» обновлён; FEATURE_COUNT → 61; schema 11 без бампа; smoke Wave AF + dist.

## AC — Ctrl+F и safety клавиатуры
- **Ctrl+F**: `page.on_keyboard_event` открывает оверлей поиска (desktop / native), рядом с Ctrl+N. На **web** браузер часто перехватывает Ctrl+F (поиск по странице).
- **Safety**: обработчик не срабатывает, пока фокус в TextField (`e.control` / `e.target` если API отдаёт поле; иначе обход дерева на `focused`).
- FEATURE_COUNT → 58; schema 11 без бампа; smoke Wave AC + dist.
