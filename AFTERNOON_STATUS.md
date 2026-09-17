# TaskTimer — статус после полудня (Wave AP)

**Дата:** 2026-09-12  
**Для:** parent deploy (`TaskTimer-dist.zip` / `TaskTimer-dist.tar.gz`)  
**Версия:** TaskTimer **1.0**, `SCHEMA_VERSION = **12**` · FEATURE_COUNT **71**

## Итог (A–AP)

Закрыты волны **A–AO** (в т.ч. Wave AG — брифинг, Wave AH — вечерний режим, Wave AI — план на завтра, Wave AJ — недельная цель, Wave AK — +1д просроченным, Wave AL — заморозка серии, Wave AM — заметка сессии фокуса, Wave AN — фильтр истории фокуса, Wave AO — заметки фокуса в аналитике); добита **Wave AP** — тап заметки → Фокус.

### Schema
- **`SCHEMA_VERSION = 12`** — без бампа (колонка `time_sessions.note` уже есть с AM).

### Wave AP
- Тап по snippet в секции «Заметки фокуса» на Аналитике → `on_open_focus` (как на Доме) открывает экран Фокуса.
- `build_analytics(..., on_open_focus=go_focus)` из `main`.
- Fallback: без колбэка — копия snippet в буфер + snack «Заметка скопирована».
- About: FEATURE_COUNT **71**, волны A–AP.

### Проверки и артефакты
- `scripts/smoke_test.py` — Wave AP asserts; **двойной прогон → `SMOKE_OK`**
- Чистый dist: `/workspace/TaskTimer-dist.zip`, `/workspace/TaskTimer-dist.tar.gz`

**SMOKE_OK** ×2. Wave AP готова.

## Wave AQ
Холст (infinite canvas) + Markdown vault + note editor; schema 13; nav «Холст».
