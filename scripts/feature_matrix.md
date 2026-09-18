# TaskTimer — матрица фич (волны A–AV)

Краткий one-pager возможностей. Локальное приложение (Flet + SQLite).

| Волна | Фича | Где |
|------:|------|-----|
| **A** | Ядро: задачи, цели, квоты, прогресс-логи, тёмный UI | Дом, Создать, Цели |
| **B** | Подзадачи, статусы, приоритеты, метки цвета | Задачи, деталь задачи |
| **C** | Фокус-таймер (помодоро), сессии | Фокус, Настройки |
| **D** | Роадмап: узлы, связи, статусы узлов | Роадмап |
| **E** | Аналитика: распределение, 14 дней, heatmap | Аналитика, Дом |
| **F** | Настройки: имя, акцент, неделя с Пн, экспорт JSON | Настройки |
| **G** | Импорт merge/replace + soft-undo снимка | Настройки |
| **H** | Глобальный поиск, сортировки, markdown-lite (`**жирный**`) | Поиск, карточки |
| **I** | Онбординг (3 карточки), целостность `current_value` целей | Дом / Настройки |
| **J** | Повтор онбординга, пакетный архив задач, список связей | Задачи, Роадмап |
| **K** | Закрепление задач, история фокуса, полоска недели | Дом, Задачи, Фокус |
| **L** | Дубликат задачи, фильтр по `color_tag` | Задачи, деталь |
| **M** | Относительные сроки (сегодня/завтра/просрочено), сводка недели, bulk complete / clear done | Дом, Задачи |
| **N** | Прогноз дней до цели, тихие часы, empty-state с emoji | Цель, Дом, Настройки |
| **O** | Прогноз целей в аналитике, мета последнего экспорта, ежедневный tip на Доме | Аналитика, Настройки, Дом |
| **P** | Шаблоны задач (Срочное / Обычное / Повтор daily), авто-раскладка роадмапа | Создать, Роадмап |
| **Q** | Защита от `AttributeError` на Доме, quiet/tips без meta, goal-mode шаблонов | Дом, Создать |
| **R** | `estimated_min` + оценка на сегодня; snooze +1/+7; auto-complete по подзадачам; «Обзор недели»; celebration 100%; polish квот | Задача, Дом, Настройки, Аналитика |
| **S** | CHANGELOG.md (RU A–R), README/matrix, чистый dist, install.ps1, double smoke | Docs / release |
| **T** | Momentum score (импульс), блок «Застой» целей | Дом |
| **U** | Итог дня (квоты/задачи/фокус/совет), сброс celebration-флагов | Дом, Настройки |
| **V** | Умный совет на Доме (застой/просрочка/квота), snack размера экспорта | Дом, Настройки |
| **W** | Пресеты 15/5 и 50/10 на Фокусе; badge активных задач; harden dismiss совета | Фокус, Нав, Дом |
| **X** | Inbox / быстрый захват; заметка дня; undo Готово; CSV; undo лога (30с); compact_ui | Дом, Задачи, Настройки |
| **Y** | Недавние поиски (meta JSON) + сортировка целей по % desc на Доме | Поиск, Дом |
| **Z** | About: версия / schema / счётчик фич / README | Настройки |
| **AA** | Горячие клавиши (жесты RU); напоминание бэкапа 7д на Доме | Настройки, Дом |
| **AB** | Ctrl+N → создать (desktop); dismiss бэкап-tip на сегодня | main, Дом |
| **AC** | Ctrl+F → поиск (desktop); shortcuts не срабатывают в TextField | main |
| **AD** | Esc → закрыть оверлей (search/create/settings/focus/detail), не в TextField | main |
| **AE** | 1/2/3/4 → вкладки Дом/Задачи/Карта/Статы на main, не в TextField | main |
| **AF** | Пробел → Фокус-таймер на main, не в TextField | main |
| **AG** | Утренний брифинг: просрочено / сегодня / квоты / импульс / совет | Дом |
| **AH** | Вечерний режим: soft-card с часа wind_down_hour + незакрытые квоты / итог дня | Дом, Настройки |
| **AI** | План на завтра: due tomorrow + open today + tip | Дом |
| **AJ** | Недельная цель задач: weekly_task_target + бар «Неделя: X/Y» | Дом, Аналитика, Настройки |
| **AK** | Отложить все просроченные +1д с баннера на Доме | Дом |
| **AL** | Заморозка серии: meta streak_freeze_used_week + 1 gap | Настройки, streak |
| **AM** | Заметка сессии фокуса: `time_sessions.note` + TextField / complete | Фокус, schema 12 |
| **AN** | Фильтр истории фокуса: чипы Все / С заметкой + текст заметки под строкой | Фокус |
| **AO** | Аналитика: последние 5 завершённых сессий с заметкой (title + snippet) | Аналитика |
| **AP** | Тап заметки фокуса в Аналитике → экран Фокуса (`on_open_focus`) / clipboard fallback | Аналитика, main |
| **AQ** | Холст infinite canvas + MD vault (`data/notes`), schema 13, FEATURE 72 | Холст |
| **AR** | PIN-лок (PBKDF2) + splash/setup/lock + `assets/icon.png`, FEATURE 73 | Лок, Настройки |
| **AS** | iOS IPA ready: pyproject / fullscreen iPhone / icon_ios / IOS_BUILD.md, FEATURE 74 | Packaging, main |
| **AT** | UX polish: Home density / toasts / validation / headers, FEATURE 75 | Дом, dialogs, Настройки |
| **AU** | Холст blank-panel fix: GestureDetector/Stack pan/zoom, height floor | Холст |
| **AV** | Фильтры в BottomSheet + haptics/motion, FEATURE 77 | Задачи, Фокус, Настройки |

**Инфра:** schema `13` (бамп AQ: `canvas_nodes`/`canvas_edges` + MD vault; AM: `time_sessions.note`), индексы SQLite, seed без double-seed, `CHANGELOG.md`, чистый dist zip, `install.ps1`, `scripts/smoke_test.py` → `SMOKE_OK` (A–AV).
