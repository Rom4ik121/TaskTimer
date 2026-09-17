"""Markdown vault — files next to SQLite under data/notes/."""
from __future__ import annotations

import re
from pathlib import Path

from app.db import get_db_path

SECTION_FILES: dict[str, str] = {
    "home": "home.md",
    "tasks": "tasks.md",
    "goals": "goals.md",
    "focus": "focus.md",
    "analytics": "analytics.md",
    "roadmap": "roadmap.md",
}

SECTION_TITLES_RU: dict[str, str] = {
    "home": "Дом",
    "tasks": "Задачи",
    "goals": "Цели",
    "focus": "Фокус",
    "analytics": "Аналитика",
    "roadmap": "Роадмап",
}

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-.]{0,120}\.md$")

_STARTER: dict[str, str] = {
    "home.md": """# Дом

Добро пожаловать в **TaskTimer**.

## Сегодня
- Проверьте квоты целей
- Закройте просроченные задачи
- Запустите [Фокус](focus.md)

## Быстрые ссылки
- [Задачи](tasks.md)
- [Цели](goals.md)
- [Аналитика](analytics.md)
- [Холст / Роадмап](roadmap.md)

> Заметки хранятся как Markdown рядом с базой — как vault в Obsidian.
""",
    "tasks.md": """# Задачи

Список дел, приоритеты и сроки.

## Советы
1. Закрепляйте важное
2. Используйте **чек-листы**
3. Повторы: daily / weekly

### Inbox
Быстрый захват с Дома попадает во входящие.

- [ ] Разобрать входящие
- [ ] Проставить сроки
""",
    "goals.md": """# Цели

Долгосрочный прогресс с дневными квотами.

## Активные
- Книга / фитнес / учёба — логируйте прогресс каждый день
- Смотрите **прогноз** на Статах

```text
квота × дни ≈ цель
```
""",
    "focus.md": """# Фокус

Pomodoro / глубокая работа.

## Ритуал
1. Выберите задачу
2. Запустите таймер
3. После сессии — короткая заметка

Ссылки: [Дом](home.md) · [Задачи](tasks.md)
""",
    "analytics.md": """# Аналитика

Статистика завершения, фокус за неделю, серии и heatmap.

## Смотрите
- Donut статусов
- Прогноз целей
- Заметки фокуса

*Данные локальные — SQLite + этот vault.*
""",
    "roadmap.md": """# Роадмап

Карта зависимостей проекта.

Узлы и рёбра живут в БД; этот файл — **заметки к карте**.

## Идея спринта
- [ ] MVP UI
- [ ] Цели + квоты
- [ ] Релиз

Откройте вкладку **Холст** для бесконечной доски.
""",
}


def notes_dir() -> Path:
    """Vault root: ``<project>/data/notes`` next to SQLite."""
    return get_db_path().parent / "notes"


def ensure_vault() -> Path:
    """Create vault dir and seed starter section files if missing."""
    root = notes_dir()
    root.mkdir(parents=True, exist_ok=True)
    for fname, body in _STARTER.items():
        path = root / fname
        if not path.exists():
            path.write_text(body, encoding="utf-8")
    return root


def sanitize_filename(name: str) -> str:
    """Return a safe ``*.md`` basename or raise ValueError."""
    raw = (name or "").strip().replace("\\", "/").split("/")[-1]
    if not raw.endswith(".md"):
        raw = raw + ".md"
    if not _SAFE_NAME.match(raw):
        raise ValueError(f"unsafe note name: {name!r}")
    if ".." in raw or raw.startswith("."):
        raise ValueError(f"unsafe note name: {name!r}")
    return raw


def _resolve(name: str) -> Path:
    """Resolve to a flat file under the vault; block path escape."""
    ensure_vault()
    safe = sanitize_filename(name)
    root = notes_dir().resolve()
    path = (root / safe).resolve()
    # Flat vault only: parent must be the vault root (blocks startswith tricks
    # like ``…/notes_evil/x.md`` and any ``..`` residual after resolve).
    if path.parent != root or not path.is_relative_to(root):
        raise ValueError("path escape blocked")
    return path


def list_notes() -> list[str]:
    """Sorted list of ``*.md`` basenames in the vault."""
    root = ensure_vault()
    return sorted(p.name for p in root.glob("*.md") if p.is_file())


def read_note(name: str) -> str:
    path = _resolve(name)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_note(name: str, content: str) -> str:
    """Write note content; returns sanitized filename."""
    path = _resolve(name)
    path.write_text(content if content is not None else "", encoding="utf-8")
    return path.name


def create_note(name: str, content: str = "") -> str:
    """Create a new note; fails if file already exists (unless empty create ok)."""
    path = _resolve(name)
    if path.exists():
        raise FileExistsError(path.name)
    body = content
    if not body:
        title = path.stem.replace("-", " ").replace("_", " ").title()
        body = f"# {title}\n\n"
    path.write_text(body, encoding="utf-8")
    return path.name


def section_filename(section_key: str) -> str:
    key = (section_key or "").strip().lower()
    if key in SECTION_FILES:
        return SECTION_FILES[key]
    # already a filename?
    return sanitize_filename(section_key if section_key.endswith(".md") else f"{key}.md")


def note_exists(name: str) -> bool:
    try:
        return _resolve(name).exists()
    except ValueError:
        return False
