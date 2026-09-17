"""Flet packaging entrypoint — delegates to ``app.main:main``.

``flet build ipa`` / ``flet run`` resolve ``[tool.flet.app] module = "main"``
relative to the project root. Desktop / smoke keep importing ``app.main``.
"""
from __future__ import annotations

from app.main import main
from app.ui.theme import ASSETS_DIR

import flet as ft

if __name__ == "__main__":
    ft.run(main, assets_dir=str(ASSETS_DIR))
