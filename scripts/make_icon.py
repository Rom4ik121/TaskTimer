#!/usr/bin/env python3
"""Generate assets/icon.png (and icon.ico) — charcoal + orange timer ring."""
from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

BG = (0x0F, 0x0F, 0x12, 255)
ORANGE = (0xFF, 0x8A, 0x00, 255)


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def write_png(path: Path, width: int, height: int, rgba: bytes) -> None:
    raw = b"".join(
        b"\x00" + rgba[y * width * 4 : (y + 1) * width * 4] for y in range(height)
    )
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(raw, 9))
        + _chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def write_ico(path: Path, png_bytes: bytes, size: int) -> None:
    # PNG-compressed ICO (Vista+). size 256 encoded as 0 in the directory.
    wh = 0 if size >= 256 else size
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", wh, wh, 0, 0, 1, 32, len(png_bytes), 22)
    path.write_bytes(header + entry + png_bytes)


def _blend(bg: tuple[int, int, int, int], fg: tuple[int, int, int, int], a: float) -> tuple[int, int, int, int]:
    a = max(0.0, min(1.0, a))
    return tuple(int(round(b * (1.0 - a) + f * a)) for b, f in zip(bg, fg))  # type: ignore[return-value]


def render_icon(size: int) -> bytes:
    cx = cy = (size - 1) / 2.0
    radius = size * 0.30
    stroke = size * 0.072
    inner_r = size * 0.055
    # Gap around 12–2 o'clock so the mark reads as a timer, not a full circle.
    gap_start = math.radians(-100)
    gap_end = math.radians(-20)
    cap_ang = gap_end
    pixels = bytearray(size * size * 4)

    def put(x: int, y: int, color: tuple[int, int, int, int]) -> None:
        i = (y * size + x) * 4
        pixels[i : i + 4] = bytes(color)

    for y in range(size):
        for x in range(size):
            dx = x - cx
            dy = y - cy
            dist = math.hypot(dx, dy)
            ang = math.atan2(dy, dx)
            color = BG
            # Ring coverage (anti-aliased annulus)
            ring = 1.0 - abs(dist - radius) / (stroke * 0.5)
            ring = max(0.0, min(1.0, ring))
            in_gap = gap_start <= ang <= gap_end
            if ring > 0 and not in_gap:
                # Soften the gap edges
                edge = min(abs(ang - gap_start), abs(ang - gap_end))
                if edge < math.radians(6):
                    ring *= edge / math.radians(6)
                color = _blend(color, ORANGE, ring)
            # Leading cap (timer head)
            cap_x = cx + radius * math.cos(cap_ang)
            cap_y = cy + radius * math.sin(cap_ang)
            cap = 1.0 - math.hypot(x - cap_x, y - cap_y) / (stroke * 0.72)
            if cap > 0:
                color = _blend(color, ORANGE, max(0.0, min(1.0, cap)))
            # Inner hub
            hub = 1.0 - abs(dist - inner_r) / (stroke * 0.22)
            hub = max(0.0, min(1.0, hub))
            if hub > 0:
                color = _blend(color, ORANGE, hub * 0.95)
            put(x, y, color)
    return bytes(pixels)


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    png_path = ASSETS / "icon.png"
    ico_path = ASSETS / "icon.ico"
    big = render_icon(512)
    write_png(png_path, 512, 512, big)
    small_rgba = render_icon(256)
    tmp = ASSETS / "_icon256.png"
    write_png(tmp, 256, 256, small_rgba)
    write_ico(ico_path, tmp.read_bytes(), 256)
    tmp.unlink(missing_ok=True)
    print(f"wrote {png_path} ({png_path.stat().st_size} bytes)")
    print(f"wrote {ico_path} ({ico_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
