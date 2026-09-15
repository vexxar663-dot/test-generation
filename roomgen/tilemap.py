"""Планировка этажа → сетка тайлов школы.

Это слой, который в Godot ляжет в `TileMapLayer`. Только stdlib —
переносится в GDScript без изменений.

Планировка школьная, а не «цепочка комнат»:

* ряды кабинетов стоят вплотную друг к другу, общими стенами;
* между рядами идёт сквозной коридор во всю длину — из него и заходят в
  кабинеты, по нему же можно пройти мимо, не заходя никуда;
* коридоры соединяются между собой через комнаты (кабинет с двумя выходами)
  и через вертикальные переходы в пустых ячейках сетки — отсюда «зацикленность»;
* лестничная площадка не выходит в коридор вообще: только из комнаты босса.

Масштаб взят от спрайтов: дверь из `walls/floor_walls.png` — 35×60 px при
реальных 0.9×2.05 м, значит тайл 16 px ≈ 0.41 м. Кабинет 20×15 тайлов
внутри — это 8.2×6.2 м, обычный школьный класс; коридор 6 тайлов — 2.5 м.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .config import Cell, RoomType

TileXY = Tuple[int, int]


class Tile(Enum):
    EMPTY = 0
    FLOOR = 1
    WALL = 2
    DOORWAY = 3   # проём: тут стоит дверь между комнатой и коридором
    HALL = 4      # пол коридора — отдельно, чтобы красить школьной плиткой


WALKABLE = (Tile.FLOOR, Tile.HALL, Tile.DOORWAY)

#: Блок кабинета в тайлах (вместе со стенами) и высота коридора.
ROOM_W = 22
ROOM_H = 17
HALL = 6
DOOR_W = 4        # ширина проёма
APPROACH = 2      # тайлов перед проёмом внутри комнаты держим пустыми

#: Комнаты, которым не нужен целый класс: занимают часть блока.
ROOM_SIZES: Dict[RoomType, Tuple[int, int]] = {
    RoomType.CHEST: (14, 11),
    RoomType.TOILET: (12, 11),
    RoomType.STAIRS: (12, 13),
}


@dataclass
class TileMap:
    width: int
    height: int
    tiles: List[List[Tile]]
    owner: Dict[TileXY, Cell] = field(default_factory=dict)
    room_rects: Dict[Cell, Tuple[int, int, int, int]] = field(default_factory=dict)
    #: r → диапазон x сквозного коридора между рядами r и r+1 (или None)
    halls: Dict[int, Tuple[int, int]] = field(default_factory=dict)
    reserved: Set[TileXY] = field(default_factory=set)

    def at(self, x: int, y: int) -> Tile:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.tiles[y][x]
        return Tile.EMPTY

    def set(self, x: int, y: int, t: Tile) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.tiles[y][x] = t

    def interior(self, cell: Cell) -> List[TileXY]:
        """Свободные тайлы пола комнаты — куда можно ставить предметы."""
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


# ---------------------------------------------------------------------------
# Геометрия
# ---------------------------------------------------------------------------

def _block(cell: Cell) -> Tuple[int, int, int, int]:
    """Блок ячейки сетки: кабинеты в ряду стоят вплотную, ряды разделены коридором."""
    r, c = cell
    return c * ROOM_W, r * (ROOM_H + HALL), ROOM_W, ROOM_H


def _hall_band(r: int) -> Tuple[int, int]:
    """Полоса y сквозного коридора между рядами r и r+1."""
    top = r * (ROOM_H + HALL) + ROOM_H
    return top, top + HALL


def _room_rect(cell: Cell, room_type: RoomType) -> Tuple[int, int, int, int]:
    bx, by, bw, bh = _block(cell)
    rw, rh = ROOM_SIZES.get(room_type, (bw, bh))
    return bx + (bw - rw) // 2, by + (bh - rh) // 2, rw, rh


def _hall_for_door(a: Cell, b: Cell) -> int:
    """Номер коридора, через который ходят между двумя соседними комнатами."""
    if a[0] != b[0]:                 # соседи по вертикали — коридор между рядами
        return min(a[0], b[0])
    return min(a[0], 3)              # соседи по горизонтали — коридор своего ряда


# ---------------------------------------------------------------------------
# Сборка
# ---------------------------------------------------------------------------

def build(floor, link_chance: float = 0.75) -> TileMap:
    """Собрать школу по сгенерированному этажу."""
    cfg = floor.config
    width = cfg.width * ROOM_W
    height = cfg.height * ROOM_H + (cfg.height - 1) * HALL
    tm = TileMap(width, height, [[Tile.EMPTY] * width for _ in range(height)])
    import random

    rng = random.Random(floor.seed * 104729 + 7)

    # 1. Кабинеты.
    for cell in floor.rooms():
        rx, ry, rw, rh = _room_rect(cell, floor.type_at(cell))
        tm.room_rects[cell] = (rx, ry, rw, rh)
        for ty in range(ry, ry + rh):
            for tx in range(rx, rx + rw):
                edge = tx in (rx, rx + rw - 1) or ty in (ry, ry + rh - 1)
                tm.set(tx, ty, Tile.WALL if edge else Tile.FLOOR)
                tm.owner[(tx, ty)] = cell

    # 2. Какие коридоры и над какими колонками нужны.
    boss, stairs = cfg.boss, floor.stairs
    private = frozenset((boss, stairs))
    need: Dict[int, Set[int]] = {}
    direct: List[Tuple[Cell, Cell]] = []   # двери «стена в стену», без коридора
    for door in floor.doors:
        a, b = sorted(door)
        if frozenset((a, b)) == private:
            direct.append((a, b))          # лестница — только из комнаты босса
            continue
        if boss in (a, b) and a[0] == b[0]:
            direct.append((a, b))          # вход к боссу сбоку — общей стеной
            continue
        need.setdefault(_hall_for_door(a, b), set()).update({a[1], b[1]})

    # 3. Прорезаем сквозные коридоры во всю длину от крайней до крайней колонки.
    for r, cols in sorted(need.items()):
        x0 = min(cols) * ROOM_W
        x1 = (max(cols) + 1) * ROOM_W
        y0, y1 = _hall_band(r)
        tm.halls[r] = (x0, x1)
        for ty in range(y0, y1):
            for tx in range(x0, x1):
                tm.set(tx, ty, Tile.HALL)

    # 4. Двери из кабинетов в коридор: каждая комната выходит в примыкающий
    #    коридор, если он до неё дотянулся. Лестница — никогда.
    for cell in sorted(floor.rooms()):
        if floor.type_at(cell) is RoomType.STAIRS:
            continue
        r, c = cell
        for hall_r, side in ((r - 1, "north"), (r, "south")):
            span = tm.halls.get(hall_r)
            if span is None:
                continue
            bx, _by, bw, _bh = _block(cell)
            if not (span[0] <= bx and bx + bw <= span[1]):
                continue
            _open_to_hall(tm, cell, hall_r, side)

    # 5. Двери «стена в стену»: босс ↔ лестница и боковой вход к боссу.
    for a, b in direct:
        _open_direct(tm, a, b)

    # 6. Вертикальные переходы в пустых ячейках — ради петель.
    for r in range(1, cfg.height - 1):
        for c in range(cfg.width):
            if (r, c) in tm.room_rects:
                continue
            above, below = tm.halls.get(r - 1), tm.halls.get(r)
            if above is None or below is None:
                continue
            x0, x1 = _link_span(c)
            # Оба коридора должны дотягиваться до этой колонки, иначе переход
            # упрётся в пустоту и получится тупиковый рукав в никуда.
            if not (above[0] <= x0 and x1 <= above[1] and
                    below[0] <= x0 and x1 <= below[1]):
                continue
            if rng.random() >= link_chance:
                continue
            _carve_vertical_link(tm, r, c)

    # 7. Убираем проходимые куски, не связанные со спавном: орфанных коридоров
    #    на карте быть не должно, откуда бы они ни взялись.
    reachable = tm.walkable_from(tm.room_center(cfg.spawn))
    for ty in range(height):
        for tx in range(width):
            if tm.tiles[ty][tx] in WALKABLE and (tx, ty) not in reachable:
                tm.tiles[ty][tx] = Tile.EMPTY

    # 8. Стены вокруг всего, что стало проходимым.
    for ty in range(height):
        for tx in range(width):
            if tm.tiles[ty][tx] is not Tile.EMPTY:
                continue
            if any(tm.at(tx + dx, ty + dy) in WALKABLE
                   for dy in (-1, 0, 1) for dx in (-1, 0, 1)):
                tm.tiles[ty][tx] = Tile.WALL
    return tm


def _door_columns(rx: int, rw: int) -> range:
    start = rx + (rw - DOOR_W) // 2
    return range(start, start + DOOR_W)


def _open_to_hall(tm: TileMap, cell: Cell, hall_r: int, side: str) -> None:
    """Проём из комнаты в коридор + тамбур, если комната меньше своего блока."""
    rx, ry, rw, rh = tm.room_rects[cell]
    _bx, by, _bw, bh = _block(cell)
    y0, y1 = _hall_band(hall_r)
    cols = _door_columns(rx, rw)

    if side == "south":
        wall_y = ry + rh - 1
        gap = range(wall_y + 1, y0)          # пустота между стеной комнаты и коридором
        approach = range(wall_y - APPROACH, wall_y)
    else:
        wall_y = ry
        gap = range(y1, wall_y)
        approach = range(wall_y + 1, wall_y + 1 + APPROACH)

    for tx in cols:
        tm.set(tx, wall_y, Tile.DOORWAY)
        tm.reserved.add((tx, wall_y))
        for ty in gap:
            tm.set(tx, ty, Tile.HALL)
            tm.reserved.add((tx, ty))
        for ty in approach:
            tm.reserved.add((tx, ty))
    del by, bh


def _open_direct(tm: TileMap, a: Cell, b: Cell) -> None:
    """Проход между двумя комнатами напрямую, минуя коридор."""
    ax, ay, aw, ah = tm.room_rects[a]
    bx, by, bw, bh = tm.room_rects[b]
    if a[0] == b[0]:                                   # рядом по горизонтали
        left, right = (a, b) if ax < bx else (b, a)
        lx, ly, lw, lh = tm.room_rects[left]
        rx2, ry2, _rw2, rh2 = tm.room_rects[right]
        rows = range(max(ly, ry2) + (min(lh, rh2) - DOOR_W) // 2,
                     max(ly, ry2) + (min(lh, rh2) - DOOR_W) // 2 + DOOR_W)
        for ty in rows:
            for tx in range(lx + lw - 1, rx2 + 1):
                tm.set(tx, ty, Tile.DOORWAY if tx in (lx + lw - 1, rx2) else Tile.HALL)
                tm.reserved.add((tx, ty))
            for tx in range(lx + lw - 1 - APPROACH, lx + lw - 1):
                tm.reserved.add((tx, ty))
            for tx in range(rx2 + 1, rx2 + 1 + APPROACH):
                tm.reserved.add((tx, ty))
    else:                                              # рядом по вертикали
        top, bottom = (a, b) if ay < by else (b, a)
        tx0, ty0, tw0, th0 = tm.room_rects[top]
        bx2, by2, bw2, _bh2 = tm.room_rects[bottom]
        cols = range(max(tx0, bx2) + (min(tw0, bw2) - DOOR_W) // 2,
                     max(tx0, bx2) + (min(tw0, bw2) - DOOR_W) // 2 + DOOR_W)
        for tx in cols:
            for ty in range(ty0 + th0 - 1, by2 + 1):
                tm.set(tx, ty, Tile.DOORWAY if ty in (ty0 + th0 - 1, by2) else Tile.HALL)
                tm.reserved.add((tx, ty))
            for ty in range(ty0 + th0 - 1 - APPROACH, ty0 + th0 - 1):
                tm.reserved.add((tx, ty))
            for ty in range(by2 + 1, by2 + 1 + APPROACH):
                tm.reserved.add((tx, ty))
    del aw, ah, bw, bh


def _link_span(c: int) -> Tuple[int, int]:
    """Диапазон x вертикального перехода в колонке c."""
    x0 = c * ROOM_W + (ROOM_W - HALL) // 2
    return x0, x0 + HALL


def _carve_vertical_link(tm: TileMap, r: int, c: int) -> None:
    """Переход через пустую ячейку: соединяет коридоры выше и ниже неё."""
    _bx, by, _bw, bh = _block((r, c))
    x0, x1 = _link_span(c)
    for ty in range(_hall_band(r - 1)[1], by + bh + 1):
        for tx in range(x0, x1):
            tm.set(tx, ty, Tile.HALL)


def rooms_to_boss(floor, tm: TileMap) -> int:
    """Сколько комнат минимум придётся пройти от спавна до босса.

    В школьной планировке мимо большинства комнат можно пройти коридором,
    поэтому «основной путь» из ГДД перестаёт быть обязательным — важно другое:
    сколько комнат игрок пройти обязан. Считается 0-1-обходом: шаг по коридору
    бесплатный, вход в новую комнату стоит единицу.
    """
    start = tm.room_center(floor.config.spawn)
    goal = tm.room_center(floor.config.boss)
    best: Dict[TileXY, int] = {start: 0}
    room_of: Dict[TileXY, Optional[Cell]] = {}
    q = deque([(start, floor.config.spawn)])
    seen_state = {(start, floor.config.spawn)}
    while q:
        (x, y), room = q.popleft()
        cost = best[(x, y)]
        for nxt in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if tm.at(*nxt) not in WALKABLE:
                continue
            owner = tm.owner.get(nxt)
            step = 1 if (owner is not None and owner != room) else 0
            new_cost = cost + step
            if nxt in best and best[nxt] <= new_cost:
                continue
            best[nxt] = new_cost
            state = (nxt, owner if owner is not None else room)
            if state in seen_state:
                continue
            seen_state.add(state)
            (q.append if step else q.appendleft)((nxt, owner if owner else room))
    del room_of
    return best.get(goal, -1)


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
        "halls": {str(r): list(span) for r, span in sorted(tm.halls.items())},
        "tiles": {
            "size": TILE_SIZE,
            "width": tm.width,
            "height": tm.height,
            "room_block": [ROOM_W, ROOM_H],
            "hall_height": HALL,
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
