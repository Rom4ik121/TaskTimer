#!/usr/bin/env python3
"""Derive icon-192.png and icon.ico from the official assets/icon.png.

Does not invent a mark. The brand PNG must already exist.
"""
from __future__ import annotations

import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ICON = ASSETS / "icon.png"
ICON_192 = ASSETS / "icon-192.png"
ICON_ICO = ASSETS / "icon.ico"


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit(f"{path} is not a PNG")
    w, h = struct.unpack(">II", data[16:24])
    return w, h


def _ffmpeg_scale(src: Path, dest: Path, size: int) -> None:
    subprocess.check_call(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(src),
            "-vf",
            f"scale={size}:{size}:flags=lanczos",
            "-frames:v",
            "1",
            "-update",
            "1",
            str(dest),
        ]
    )


def write_ico(path: Path, png_bytes: bytes, size: int) -> None:
    wh = 0 if size >= 256 else size
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", wh, wh, 0, 0, 1, 32, len(png_bytes), 22)
    path.write_bytes(header + entry + png_bytes)


def main() -> int:
    if not ICON.is_file():
        print("missing official assets/icon.png — will not invent a mark", file=sys.stderr)
        return 1
    w, h = _png_size(ICON)
    print(f"official icon {ICON} {w}x{h}")
    _ffmpeg_scale(ICON, ICON_192, 192)
    tmp = ASSETS / "_icon256.png"
    _ffmpeg_scale(ICON, tmp, 256)
    write_ico(ICON_ICO, tmp.read_bytes(), 256)
    tmp.unlink(missing_ok=True)
    print(f"wrote {ICON_192} ({ICON_192.stat().st_size} bytes)")
    print(f"wrote {ICON_ICO} ({ICON_ICO.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
