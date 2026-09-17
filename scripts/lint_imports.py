#!/usr/bin/env python3
"""Import every app screen / component / service module (catch syntax & import errors)."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Modules that must import cleanly (UI screens + shared components + services).
MODULES: list[str] = [
    "app.main",
    "app.db",
    "app.models",
    "app.schemas",
    "app.services.analytics_service",
    "app.services.canvas_service",
    "app.services.export_service",
    "app.services.notes_service",
    "app.services.lock_service",
    "app.services.goal_service",
    "app.services.reminder_service",
    "app.services.roadmap_service",
    "app.services.search_service",
    "app.services.seed",
    "app.services.settings_service",
    "app.services.streak_service",
    "app.services.subtask_service",
    "app.services.task_service",
    "app.services.timer_service",
    "app.ui.theme",
    "app.ui.components.cards",
    "app.ui.components.dialogs",
    "app.ui.components.nav",
    "app.ui.components.pin_pad",
    "app.ui.components.progress_ring",
    "app.ui.screens.analytics",
    "app.ui.screens.canvas_board",
    "app.ui.screens.create_task",
    "app.ui.screens.focus",
    "app.ui.screens.goal_detail",
    "app.ui.screens.home",
    "app.ui.screens.lock_screen",
    "app.ui.screens.pin_setup",
    "app.ui.screens.note_editor",
    "app.ui.screens.onboarding",
    "app.ui.screens.reminders",
    "app.ui.screens.roadmap",
    "app.ui.screens.search",
    "app.ui.screens.settings",
    "app.ui.screens.splash",
    "app.ui.screens.task_detail",
    "app.ui.screens.tasks",
]


def lint_imports(modules: list[str] | None = None) -> int:
    """Import each module; raise on failure. Returns count imported."""
    mods = modules or MODULES
    for name in mods:
        importlib.import_module(name)
    return len(mods)


def main() -> int:
    n = lint_imports()
    print(f"LINT_IMPORTS_OK {n}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("LINT_IMPORTS_FAIL", exc)
        raise
