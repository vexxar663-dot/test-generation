"""Планировка этажа → сетка тайлов.

Это тот самый слой, который в Godot ляжет в `TileMapLayer`: генератор отдаёт
граф комнат, а здесь он превращается в конкретные тайлы пола, стен и проёмов.
Только stdlib — переносится в GDScript без изменений.

Комната занимает блок ROOM_W×ROOM_H тайлов (внешнее кольцо — стены), между
блоками остаётся GAP тайлов под коридоры. Коридор рисуется только там, где
генератор поставил дверь: физическое соседство комнат прохода не даёт.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from .config import Cell, RoomType

TileXY = Tuple[int, int]


class Tile(Enum):
    EMPTY = 0
    FLOOR = 1
    WALL = 2
    DOORWAY = 3   # проём в стене комнаты — тут ставится дверь


#: Размер блока комнаты в тайлах (вместе со стенами) и ширина коридорной полосы.
ROOM_W = 13
ROOM_H = 9
GAP = 3           # длина коридора между блоками
CORRIDOR = 3      # ширина коридора (в тайлах)
APPROACH = 2      # сколько тайлов перед проёмом внутри комнаты держать пустыми


@dataclass
class TileMap:
    width: int
    height: int
    tiles: List[List[Tile]]
    #: тайл → комната, которой он принадлежит (None для коридоров)
    owner: Dict[TileXY, Cell] = field(default_factory=dict)
    #: комната → её блок (x, y, w, h) в тайлах
    room_rects: Dict[Cell, Tuple[int, int, int, int]] = field(default_factory=dict)
    #: тайлы коридоров и проёмов — по ним нельзя ставить предметы
    reserved: Set[TileXY] = field(default_factory=set)

    def at(self, x: int, y: int) -> Tile:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.tiles[y][x]
        return Tile.EMPTY

    def set(self, x: int, y: int, t: Tile) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.tiles[y][x] = t

    def interior(self, cell: Cell) -> List[TileXY]:
        """Свободные тайлы пола комнаты (без стен, коридорных полос и проёмов)."""
        x, y, w, h = self.room_rects[cell]
        return [
            (tx, ty)
            for ty in range(y + 1, y + h - 1)
            for tx in range(x + 1, x + w - 1)
            if (tx, ty) not in self.reserved and self.at(tx, ty) is Tile.FLOOR
        ]

    def room_center(self, cell: Cell) -> TileXY:
        x, y, w, h = self.room_rects[cell]
        return x + w // 2, y + h // 2


def _room_origin(cell: Cell) -> TileXY:
    r, c = cell
    return c * (ROOM_W + GAP), r * (ROOM_H + GAP)


def build(floor) -> TileMap:
    """Собрать сетку тайлов по сгенерированному этажу."""
    cfg = floor.config
    width = cfg.width * ROOM_W + (cfg.width - 1) * GAP
    height = cfg.height * ROOM_H + (cfg.height - 1) * GAP
    tm = TileMap(width, height, [[Tile.EMPTY] * width for _ in range(height)])

    # 1. Блоки комнат: кольцо стен + пол внутри.
    for cell in floor.rooms():
        ox, oy = _room_origin(cell)
        tm.room_rects[cell] = (ox, oy, ROOM_W, ROOM_H)
        for ty in range(oy, oy + ROOM_H):
            for tx in range(ox, ox + ROOM_W):
                edge = tx in (ox, ox + ROOM_W - 1) or ty in (oy, oy + ROOM_H - 1)
                tm.set(tx, ty, Tile.WALL if edge else Tile.FLOOR)
                tm.owner[(tx, ty)] = cell

    # 2. Коридоры — только там, где генератор поставил дверь.
    for door in floor.doors:
        a, b = sorted(door)
        _carve_corridor(tm, a, b)

    # 3. Стены вокруг всего, что стало полом.
    for ty in range(height):
        for tx in range(width):
            if tm.tiles[ty][tx] is not Tile.EMPTY:
                continue
            if any(tm.at(tx + dx, ty + dy) in (Tile.FLOOR, Tile.DOORWAY)
                   for dy in (-1, 0, 1) for dx in (-1, 0, 1)):
                tm.tiles[ty][tx] = Tile.WALL
    return tm


def _carve_corridor(tm: TileMap, a: Cell, b: Cell) -> None:
    ax, ay = _room_origin(a)
    bx, by = _room_origin(b)
    off = (ROOM_H - CORRIDOR) // 2 if a[0] == b[0] else (ROOM_W - CORRIDOR) // 2

    if a[0] == b[0]:                      # соседи по горизонтали
        lane = [ay + off + i for i in range(CORRIDOR)]
        span = range(ax + ROOM_W - 1, bx + 1)
        for ty in lane:
            for tx in span:
                door_col = tx in (ax + ROOM_W - 1, bx)
                tm.set(tx, ty, Tile.DOORWAY if door_col else Tile.FLOOR)
                tm.reserved.add((tx, ty))
            # Подход к проёму изнутри обеих комнат держим свободным от предметов.
            for depth in range(1, APPROACH + 1):
                tm.reserved.add((ax + ROOM_W - 1 - depth, ty))
                tm.reserved.add((bx + depth, ty))
    else:                                  # соседи по вертикали
        lane = [ax + off + i for i in range(CORRIDOR)]
        span = range(ay + ROOM_H - 1, by + 1)
        for tx in lane:
            for ty in span:
                door_row = ty in (ay + ROOM_H - 1, by)
                tm.set(tx, ty, Tile.DOORWAY if door_row else Tile.FLOOR)
                tm.reserved.add((tx, ty))
            for depth in range(1, APPROACH + 1):
                tm.reserved.add((tx, ay + ROOM_H - 1 - depth))
                tm.reserved.add((tx, by + depth))


#: Оформление комнаты: семейство тайлов пола + цвет кирпича стен.
THEME: Dict[RoomType, Tuple[str, str]] = {
    RoomType.SPAWN:     ("green", "brown"),
    RoomType.NORMAL:    ("school", "brown"),
    RoomType.HARD:      ("school", "red"),
    RoomType.CAFETERIA: ("parquet", "light"),
    RoomType.TOILET:    ("white", "white"),
    RoomType.CHEST:     ("blue", "orange"),
    RoomType.EVENT:     ("blue", "orange"),
    RoomType.STAIRS:    ("school", "white"),
    RoomType.BOSS:      ("red", "red"),
}
CORRIDOR_THEME = ("school", "brown")


def to_dict(floor, tm: Optional[TileMap] = None) -> dict:
    """Этаж в JSON-совместимый вид — то, что читает сцена в Godot.

    Комнаты, двери и готовая сетка тайлов; `tileset` говорит, какую вырезку
    из res://spites/floors/tiles.png класть под каждый тип комнаты.
    """
    from .sprites import FLOOR_FAMILIES, TILE_SIZE, WALL_BRICK

    tm = tm or build(floor)
    return {
        "seed": floor.seed,
        "grid": {"height": floor.config.height, "width": floor.config.width},
        "rooms": [
            {
                "cell": list(cell),
                "type": floor.type_at(cell).value,
                "rect_tiles": list(tm.room_rects[cell]),
                "doors_to": [list(n) for n in floor.linked(cell)],
            }
            for cell in sorted(floor.rooms())
        ],
        "doors": [[list(a), list(b)] for a, b in (sorted(d) for d in floor.doors)],
        "main_path": [list(c) for c in floor.main_path],
        "tiles": {
            "size": TILE_SIZE,
            "width": tm.width,
            "height": tm.height,
            "rows": ["".join(str(t.value) for t in row) for row in tm.tiles],
            "legend": {str(t.value): t.name.lower() for t in Tile},
        },
        "tileset": {
            "source": "res://spites/floors/tiles.png",
            "floor_by_room": {rt.value: THEME[rt][0] for rt in THEME},
            "wall_by_room": {rt.value: THEME[rt][1] for rt in THEME},
            "floor_families": {k: [list(r) for r in v] for k, v in FLOOR_FAMILIES.items()},
            "wall_bricks": {k: list(v) for k, v in WALL_BRICK.items()},
        },
    }
