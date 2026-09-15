"""Планировка этажа → сетка тайлов.

В свободной планировке генератор уже отдаёт комнаты прямоугольниками в тайлах,
поэтому этому слою остаётся немного: обвести комнаты стенами, положить пол,
прорезать перемычки и проёмы в стенах. Это то, что в Godot ляжет в
`TileMapLayer`. Только stdlib — переносится в GDScript без изменений.

Масштаб: тайл 16 px ≈ 0.41 м (выведен из спрайта двери, см. docs/sprites.md).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from .config import RoomId, RoomType

TileXY = Tuple[int, int]


class Tile(Enum):
    EMPTY = 0
    FLOOR = 1
    WALL = 2
    DOORWAY = 3   # проём в стене комнаты: тут стоит дверь
    HALL = 4      # пол перемычки между комнатами


WALKABLE = (Tile.FLOOR, Tile.HALL, Tile.DOORWAY)

#: Тайлов перед проёмом внутри комнаты, которые держим свободными от мебели.
APPROACH = 2


@dataclass
class TileMap:
    width: int
    height: int
    tiles: List[List[Tile]]
    owner: Dict[TileXY, RoomId] = field(default_factory=dict)
    room_rects: Dict[RoomId, Tuple[int, int, int, int]] = field(default_factory=dict)
    reserved: Set[TileXY] = field(default_factory=set)

    def at(self, x: int, y: int) -> Tile:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.tiles[y][x]
        return Tile.EMPTY

    def set(self, x: int, y: int, t: Tile) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.tiles[y][x] = t

    def interior(self, rid: RoomId) -> List[TileXY]:
        """Свободные тайлы пола комнаты — куда можно ставить предметы."""
        x, y, w, h = self.room_rects[rid]
        return [
            (tx, ty)
            for ty in range(y + 1, y + h - 1)
            for tx in range(x + 1, x + w - 1)
            if (tx, ty) not in self.reserved and self.at(tx, ty) is Tile.FLOOR
        ]

    def room_center(self, rid: RoomId) -> TileXY:
        x, y, w, h = self.room_rects[rid]
        return x + w // 2, y + h // 2

    def walkable_from(self, start: TileXY) -> Set[TileXY]:
        seen = {start}
        q = deque([start])
        while q:
            x, y = q.popleft()
            for nxt in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if nxt not in seen and self.at(*nxt) in WALKABLE:
                    seen.add(nxt)
                    q.append(nxt)
        return seen


def build(floor) -> TileMap:
    """Собрать сетку тайлов по сгенерированному этажу."""
    tm = TileMap(floor.width, floor.height,
                 [[Tile.EMPTY] * floor.width for _ in range(floor.height)])

    # 1. Комнаты: кольцо стен, внутри пол.
    for rid in floor.rooms():
        room = floor.room(rid)
        tm.room_rects[rid] = (room.x, room.y, room.w, room.h)
        for ty in range(room.y, room.y2):
            for tx in range(room.x, room.x2):
                edge = tx in (room.x, room.x2 - 1) or ty in (room.y, room.y2 - 1)
                tm.set(tx, ty, Tile.WALL if edge else Tile.FLOOR)
                tm.owner[(tx, ty)] = rid

    # 2. Перемычки и проёмы в стенах по обе стороны от них.
    for corridor in floor.corridors.values():
        for ty in range(corridor.y, corridor.y2):
            for tx in range(corridor.x, corridor.x2):
                tm.set(tx, ty, Tile.HALL)
        if corridor.axis == "h":
            for ty in range(corridor.y, corridor.y2):
                _pierce(tm, corridor.x - 1, ty, (-1, 0))
                _pierce(tm, corridor.x2, ty, (1, 0))
        else:
            for tx in range(corridor.x, corridor.x2):
                _pierce(tm, tx, corridor.y - 1, (0, -1))
                _pierce(tm, tx, corridor.y2, (0, 1))

    # 3. Стены вокруг всего, что стало проходимым.
    for ty in range(tm.height):
        for tx in range(tm.width):
            if tm.tiles[ty][tx] is not Tile.EMPTY:
                continue
            if any(tm.at(tx + dx, ty + dy) in WALKABLE
                   for dy in (-1, 0, 1) for dx in (-1, 0, 1)):
                tm.tiles[ty][tx] = Tile.WALL
    return tm


def _pierce(tm: TileMap, x: int, y: int, inward: Tuple[int, int]) -> None:
    """Проём в стене комнаты + свободная подход-полоса внутри неё."""
    tm.set(x, y, Tile.DOORWAY)
    tm.reserved.add((x, y))
    dx, dy = inward
    for step in range(1, APPROACH + 1):
        tm.reserved.add((x + dx * step, y + dy * step))


def rooms_to_boss(floor, tm: Optional[TileMap] = None) -> int:
    """Сколько комнат игрок обязан пройти от спавна до босса, считая обе.

    В свободной планировке перемычки соединяют комнату с комнатой, обойти
    комнату коридором нельзя, поэтому это просто длина кратчайшего маршрута.
    """
    del tm
    return len(floor.critical_path())


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
    """Этаж в JSON-совместимый вид — то, что читает сцена в Godot."""
    from .sprites import FLOOR_FAMILIES, TILE_SIZE, WALL_BRICK

    tm = tm or build(floor)
    return {
        "seed": floor.seed,
        "size_tiles": [floor.width, floor.height],
        "spawn": floor.spawn,
        "boss": floor.boss,
        "stairs": floor.stairs,
        "spine": list(floor.spine),
        "rooms": [
            {
                "id": rid,
                "type": floor.type_at(rid).value,
                "rect_tiles": list(tm.room_rects[rid]),
                "doors_to": floor.linked(rid),
            }
            for rid in floor.rooms()
        ],
        "corridors": [
            {
                "between": sorted(door),
                "axis": c.axis,
                "rect_tiles": [c.x, c.y, c.w, c.h],
            }
            for door, c in sorted(floor.corridors.items(), key=lambda kv: sorted(kv[0]))
        ],
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
