"""ASCII-рендер этажа — быстрая проверка в терминале без matplotlib."""

from __future__ import annotations

from typing import List, Optional

from .config import GLYPH, RU_NAME, RoomType
from .generator import Floor

__all__ = ["render", "render_summary"]

_CELL_W = 5


def render(floor: Floor, mark_main_path: bool = True) -> str:
    """Сетка с дверями: `─` между комнатами по горизонтали, `│` по вертикали.

    Комнаты основного пути помечены скобками: [ B ] вместо ( B ).
    """
    cfg = floor.config
    on_path = set(floor.main_path) if mark_main_path else set()
    lines: List[str] = []
    for r in range(cfg.height):
        row, under = "", ""
        for c in range(cfg.width):
            cell = (r, c)
            t = floor.type_at(cell)
            if t is RoomType.EMPTY:
                row += "     "
            else:
                left, right = ("[", "]") if cell in on_path else ("(", ")")
                row += f"{left} {GLYPH[t]} {right}"
            if c + 1 < cfg.width:
                row += "───" if frozenset((cell, (r, c + 1))) in floor.doors else "   "
            if r + 1 < cfg.height:
                under += "  │  " if frozenset((cell, (r + 1, c))) in floor.doors else "     "
                under += "   " if c + 1 < cfg.width else ""
        lines.append(row.rstrip())
        if r + 1 < cfg.height:
            lines.append(under.rstrip())
    return "\n".join(lines)


def render_summary(floor: Floor) -> str:
    counts = floor.counts()
    order = [
        RoomType.SPAWN, RoomType.NORMAL, RoomType.HARD, RoomType.CHEST,
        RoomType.CAFETERIA, RoomType.TOILET, RoomType.EVENT,
        RoomType.BOSS, RoomType.STAIRS,
    ]
    parts = [f"{RU_NAME[t]}: {counts.get(t, 0)}" for t in order if counts.get(t, 0)]
    crit = floor.critical_path()
    lo_all, hi_all = floor.time_estimate()
    lo_crit, hi_crit = floor.time_estimate(crit)
    return (
        f"seed={floor.seed}  попыток={floor.attempts}  комнат={len(floor.rooms())}  "
        f"дверей={len(floor.doors)}\n"
        f"основной путь: {len(floor.main_path)} клеток, "
        f"кратчайший до босса: {len(crit)} комнат\n"
        + ", ".join(parts)
        + f"\nвремя: спидран {lo_crit/60:.1f}–{hi_crit/60:.1f} мин, "
        f"на 100% {lo_all/60:.1f}–{hi_all/60:.1f} мин (ГДД: 5–7 мин)"
    )
