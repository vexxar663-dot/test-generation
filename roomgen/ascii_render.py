"""ASCII-рендер этажа — быстрая проверка в терминале без matplotlib.

Планировка свободная, поэтому этаж печатается как уменьшенная карта: каждая
комната занимает свой прямоугольник в символьной сетке, перемычки — точками.
"""

from __future__ import annotations

from typing import List, Optional

from .config import GLYPH, RU_NAME, RoomType
from .generator import Floor

__all__ = ["render", "render_summary"]

#: Сколько тайлов в одном символе по горизонтали и вертикали.
SCALE_X = 4
SCALE_Y = 8


def render(floor: Floor, mark_route: bool = True) -> str:
    """Карта этажа символами. Комнаты — рамки с глифом, перемычки — точки."""
    cols = floor.width // SCALE_X + 1
    rows = floor.height // SCALE_Y + 1
    canvas: List[List[str]] = [[" "] * cols for _ in range(rows)]
    route = set(floor.critical_path()) if mark_route else set()

    for corridor in floor.corridors.values():
        for ty in range(corridor.y, corridor.y2):
            for tx in range(corridor.x, corridor.x2):
                canvas[ty // SCALE_Y][tx // SCALE_X] = "."

    for rid in floor.rooms():
        room = floor.room(rid)
        x0, x1 = room.x // SCALE_X, (room.x2 - 1) // SCALE_X
        y0, y1 = room.y // SCALE_Y, (room.y2 - 1) // SCALE_Y
        fill = "#" if rid in route else "+"
        for ty in range(y0, y1 + 1):
            for tx in range(x0, x1 + 1):
                edge = tx in (x0, x1) or ty in (y0, y1)
                canvas[ty][tx] = fill if edge else " "
        canvas[(y0 + y1) // 2][(x0 + x1) // 2] = GLYPH[room.type]

    return "\n".join("".join(row).rstrip() for row in canvas)


def render_summary(floor: Floor) -> str:
    counts = floor.counts()
    order = [
        RoomType.SPAWN, RoomType.NORMAL, RoomType.HARD, RoomType.CHEST,
        RoomType.CAFETERIA, RoomType.TOILET, RoomType.EVENT,
        RoomType.BOSS, RoomType.STAIRS,
    ]
    parts = [f"{RU_NAME[t]}: {counts.get(t, 0)}" for t in order if counts.get(t, 0)]
    route = floor.critical_path()
    loops = len(floor.corridors) - len(floor.rooms()) + 1
    lo_all, hi_all = floor.time_estimate()
    lo_rt, hi_rt = floor.time_estimate(route)
    return (
        f"seed={floor.seed}  попыток={floor.attempts}  комнат={len(floor.rooms())}  "
        f"перемычек={len(floor.corridors)}  петель={loops}\n"
        f"обязательный маршрут до босса: {len(route)} комнат (ГДД 3.1: 5–6), "
        f"этаж {floor.width}×{floor.height} тайлов\n"
        + ", ".join(parts)
        + f"\nвремя: спидран {lo_rt/60:.1f}–{hi_rt/60:.1f} мин, "
        f"на 100% {lo_all/60:.1f}–{hi_all/60:.1f} мин (ГДД: 5–7 мин)"
    )
