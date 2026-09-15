"""Генерация этажа «Equation Dodge»: свободная упаковка комнат.

Сетки нет. Этаж выращивается от спавна: каждая новая комната пристраивается к
уже стоящей с одной из четырёх сторон, на коротком коридоре, и принимается,
только если её прямоугольник ни с чем не пересёкся. Форма этажа получается из
порядка роста и размеров комнат, а не из ячеек — как на концепт-схеме.

Порядок построения:
  1. состав этажа по лимитам ГДД 3.2;
  2. хребет: обязательный маршрут спавн → босс длиной 5–6 комнат (ГДД 3.1);
  3. лестничная площадка — только от комнаты босса;
  4. ответвления до нужного числа комнат, на концах — сундук/столовая/толчок;
  5. усложнённые и ивентовая комнаты;
  6. петли — лишние связи, не укорачивающие маршрут до босса;
  7. проверка (validation.py).

Зависимостей нет, только stdlib: модуль переносится в GDScript один в один.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple

from .config import (
    PROTECTED_TYPES,
    ROOM_SECONDS,
    TERMINAL_TYPES,
    TRANSITION_SECONDS,
    GenConfig,
    RoomId,
    RoomType,
)

Door = FrozenSet[RoomId]

#: Четыре стороны: имя → (dx, dy) в тайлах.
DIRECTIONS: Dict[str, Tuple[int, int]] = {
    "E": (1, 0), "W": (-1, 0), "S": (0, 1), "N": (0, -1),
}
OPPOSITE = {"E": "W", "W": "E", "S": "N", "N": "S"}


class GenerationError(RuntimeError):
    """Не удалось собрать корректный этаж за max_attempts попыток."""


@dataclass(frozen=True)
class Room:
    """Комната как прямоугольник в тайлах. Стены входят в размер."""

    id: RoomId
    type: RoomType
    x: int
    y: int
    w: int
    h: int

    @property
    def x2(self) -> int:
        return self.x + self.w

    @property
    def y2(self) -> int:
        return self.y + self.h

    @property
    def center(self) -> Tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2

    def moved(self, dx: int, dy: int) -> "Room":
        return Room(self.id, self.type, self.x + dx, self.y + dy, self.w, self.h)

    def retyped(self, room_type: RoomType) -> "Room":
        return Room(self.id, room_type, self.x, self.y, self.w, self.h)

    def overlaps(self, other: "Room", margin: int = 0) -> bool:
        return not (
            self.x2 + margin <= other.x or other.x2 + margin <= self.x
            or self.y2 + margin <= other.y or other.y2 + margin <= self.y
        )


@dataclass(frozen=True)
class Corridor:
    """Прямая перемычка между стенами двух комнат."""

    a: RoomId
    b: RoomId
    axis: str      # "h" — горизонтальная перемычка, "v" — вертикальная
    x: int
    y: int
    w: int
    h: int

    @property
    def x2(self) -> int:
        return self.x + self.w

    @property
    def y2(self) -> int:
        return self.y + self.h

    def moved(self, dx: int, dy: int) -> "Corridor":
        return Corridor(self.a, self.b, self.axis, self.x + dx, self.y + dy, self.w, self.h)

    def hits(self, room: Room, margin: int = 0) -> bool:
        return not (
            self.x2 + margin <= room.x or room.x2 + margin <= self.x
            or self.y2 + margin <= room.y or room.y2 + margin <= self.y
        )


@dataclass
class Floor:
    """Готовый этаж: комнаты, перемычки и обязательный маршрут до босса."""

    rooms_by_id: Dict[RoomId, Room]
    corridors: Dict[Door, Corridor]
    spine: List[RoomId]
    spawn: RoomId
    boss: RoomId
    stairs: RoomId
    seed: int
    attempts: int
    config: GenConfig
    width: int = 0
    height: int = 0

    # --- доступ -----------------------------------------------------------
    @property
    def doors(self) -> Set[Door]:
        return set(self.corridors)

    def rooms(self) -> List[RoomId]:
        return sorted(self.rooms_by_id)

    def room(self, rid: RoomId) -> Room:
        return self.rooms_by_id[rid]

    def type_at(self, rid: RoomId) -> RoomType:
        return self.rooms_by_id[rid].type

    def linked(self, rid: RoomId) -> List[RoomId]:
        out = [next(iter(d - {rid})) for d in self.corridors if rid in d]
        return sorted(out)

    def degree(self, rid: RoomId) -> int:
        return sum(1 for d in self.corridors if rid in d)

    def is_dead_end(self, rid: RoomId) -> bool:
        return self.degree(rid) == 1

    def counts(self) -> Dict[RoomType, int]:
        res: Dict[RoomType, int] = {}
        for room in self.rooms_by_id.values():
            res[room.type] = res.get(room.type, 0) + 1
        return res

    def distances_from_spawn(self) -> Dict[RoomId, int]:
        dist = {self.spawn: 0}
        q = deque([self.spawn])
        while q:
            cur = q.popleft()
            for nxt in self.linked(cur):
                if nxt not in dist:
                    dist[nxt] = dist[cur] + 1
                    q.append(nxt)
        return dist

    def critical_path(self) -> List[RoomId]:
        """Кратчайший маршрут спавн → босс по перемычкам."""
        prev: Dict[RoomId, Optional[RoomId]] = {self.spawn: None}
        q = deque([self.spawn])
        while q:
            cur = q.popleft()
            if cur == self.boss:
                break
            for nxt in self.linked(cur):
                if nxt not in prev:
                    prev[nxt] = cur
                    q.append(nxt)
        if self.boss not in prev:
            return []
        path, node = [], self.boss
        while node is not None:
            path.append(node)
            node = prev[node]
        return list(reversed(path))

    # --- тайминг (ГДД «Тайминг прохождения этажа») ------------------------
    def time_estimate(self, ids: Optional[Sequence[RoomId]] = None) -> Tuple[float, float]:
        ids = list(self.rooms()) if ids is None else list(ids)
        lo = hi = 0.0
        for rid in ids:
            a, b = ROOM_SECONDS[self.type_at(rid)]
            lo += a
            hi += b
        moves = max(len(ids) - 1, 0)
        return lo + moves * TRANSITION_SECONDS, hi + moves * TRANSITION_SECONDS


# ---------------------------------------------------------------------------
# Вспомогательное
# ---------------------------------------------------------------------------

def _pick_weighted(rng: random.Random, pairs: Sequence[Tuple]) -> object:
    total = sum(w for _, w in pairs)
    roll = rng.random() * total
    upto = 0.0
    for value, weight in pairs:
        upto += weight
        if roll <= upto:
            return value
    return pairs[-1][0]


# ---------------------------------------------------------------------------
# Построитель — один проход генерации
# ---------------------------------------------------------------------------

class _Builder:
    def __init__(self, cfg: GenConfig, rng: random.Random):
        self.cfg = cfg
        self.rng = rng
        self.rooms: Dict[RoomId, Room] = {}
        self.corridors: Dict[Door, Corridor] = {}
        self.counts: Dict[RoomType, int] = {}
        self.spine: List[RoomId] = []
        self.terminal_queue: List[RoomType] = []
        self.hard_on_spine = 0
        self._next_id = 0
        # Куда «тянется» этаж: босс уходит в эту сторону от спавна.
        angle = rng.random() * 6.283185
        import math

        self.drift = (math.cos(angle), math.sin(angle))

    # --- примитивы --------------------------------------------------------
    def cap_of(self, t: RoomType) -> int:
        return self.cfg.caps.get(t, (0, 10 ** 6))[1]

    def can_place(self, t: RoomType) -> bool:
        return self.counts.get(t, 0) < self.cap_of(t)

    def _size(self, t: RoomType) -> Tuple[int, int]:
        (wlo, whi), (hlo, hhi) = self.cfg.sizes[t]
        return self.rng.randint(wlo, whi), self.rng.randint(hlo, hhi)

    def _fits(self, room: Room, corridor: Optional[Corridor]) -> bool:
        margin = self.cfg.room_margin
        for other in self.rooms.values():
            if room.overlaps(other, margin):
                return False
            if corridor is not None and other.id not in (corridor.a, corridor.b) \
                    and corridor.hits(other, 1):
                return False
        if corridor is not None:
            for existing in self.corridors.values():
                if _boxes_touch(corridor, existing, 1):
                    return False
        return True

    def attach(self, anchor_id: RoomId, room_type: RoomType,
               prefer_drift: bool = False) -> Optional[RoomId]:
        """Пристроить комнату к anchor с любой стороны. None — не поместилась."""
        if not self.can_place(room_type):
            return None
        anchor = self.rooms[anchor_id]
        order = self._direction_order(anchor, prefer_drift)
        for _ in range(self.cfg.placement_tries):
            side = order[self.rng.randrange(len(order))] if order else None
            if side is None:
                return None
            w, h = self._size(room_type)
            placed = self._try_side(anchor, side, w, h, room_type)
            if placed is not None:
                room, corridor = placed
                self.rooms[room.id] = room
                self.corridors[frozenset((anchor_id, room.id))] = corridor
                self.counts[room_type] = self.counts.get(room_type, 0) + 1
                return room.id
        return None

    def _direction_order(self, anchor: Room, prefer_drift: bool) -> List[str]:
        """Стороны в случайном порядке; для хребта — с уклоном «от спавна»."""
        sides = list(DIRECTIONS)
        if not prefer_drift:
            self.rng.shuffle(sides)
            return sides
        dx, dy = self.drift
        weighted = []
        for side in sides:
            vx, vy = DIRECTIONS[side]
            weighted.append((side, max(0.15, 1.0 + 2.2 * (vx * dx + vy * dy))))
        order: List[str] = []
        pool = list(weighted)
        while pool:
            chosen = _pick_weighted(self.rng, pool)
            order.append(chosen)
            pool = [p for p in pool if p[0] != chosen]
        return order

    def _try_side(self, anchor: Room, side: str, w: int, h: int,
                  room_type: RoomType) -> Optional[Tuple[Room, Corridor]]:
        cfg = self.cfg
        gap = self.rng.randint(*cfg.corridor_length)
        need = cfg.corridor_width + 2          # проём плюс по стене с каждой стороны

        if side in ("E", "W"):
            if min(anchor.h, h) < need:
                return None
            lo = anchor.y - (h - need)
            hi = anchor.y + anchor.h - need
            y = self.rng.randint(lo, hi)
            x = anchor.x2 + gap if side == "E" else anchor.x - gap - w
            room = Room(self._next_id, room_type, x, y, w, h)
            o0, o1 = max(anchor.y, y) + 1, min(anchor.y2, y + h) - 1
            if o1 - o0 < cfg.corridor_width:
                return None
            cy = self.rng.randint(o0, o1 - cfg.corridor_width)
            cx = anchor.x2 if side == "E" else x + w
            corridor = Corridor(anchor.id, room.id, "h", cx, cy, gap, cfg.corridor_width)
        else:
            if min(anchor.w, w) < need:
                return None
            lo = anchor.x - (w - need)
            hi = anchor.x + anchor.w - need
            x = self.rng.randint(lo, hi)
            y = anchor.y2 + gap if side == "S" else anchor.y - gap - h
            room = Room(self._next_id, room_type, x, y, w, h)
            o0, o1 = max(anchor.x, x) + 1, min(anchor.x2, x + w) - 1
            if o1 - o0 < cfg.corridor_width:
                return None
            cx = self.rng.randint(o0, o1 - cfg.corridor_width)
            cy = anchor.y2 if side == "S" else y + h
            corridor = Corridor(anchor.id, room.id, "v", cx, cy, cfg.corridor_width, gap)

        if not self._fits(room, corridor):
            return None
        self._next_id += 1
        return room, corridor

    # --- шаги -------------------------------------------------------------
    def seed_spawn(self) -> RoomId:
        room = Room(self._next_id, RoomType.SPAWN, 0, 0, *self._size(RoomType.SPAWN))
        self._next_id += 1
        self.rooms[room.id] = room
        self.counts[RoomType.SPAWN] = 1
        self.spine = [room.id]
        return room.id

    def plan_specials(self) -> None:
        """Заранее решить, каких особых комнат сколько и где.

        Тип выбирается ДО постановки, потому что от типа зависит размер:
        сундук маленький, усложнённая большая, столовая широкая. Если менять
        тип уже поставленной комнате, размер остаётся чужим — на концепт-схеме
        размер как раз и читается как тип.
        """
        cfg = self.cfg
        hard_total = self.rng.randint(*cfg.hard_rooms)
        # ГДД 3.4 шаг 5: тупик предпочтительнее, основной путь — реже.
        self.hard_on_spine = sum(
            1 for _ in range(hard_total)
            if self.rng.random() >= cfg.hard_dead_end_preference
        )
        queue: List[RoomType] = [RoomType.CHEST] * cfg.caps[RoomType.CHEST][0]
        queue += [RoomType.HARD] * (hard_total - self.hard_on_spine)
        if self.rng.random() < cfg.event_chance:
            queue.append(RoomType.EVENT)
        self.rng.shuffle(queue)
        self.terminal_queue = queue

    def grow_spine(self) -> bool:
        """Обязательный маршрут спавн → босс длиной 5–6 комнат (ГДД 3.1)."""
        target = self.rng.randint(*self.cfg.spine_rooms)
        middle = target - 2
        hard_slots = set(self.rng.sample(range(middle), min(self.hard_on_spine, middle))) \
            if middle else set()
        for i in range(middle):
            room_type = RoomType.HARD if i in hard_slots else RoomType.NORMAL
            new_id = self.attach(self.spine[-1], room_type, prefer_drift=True)
            if new_id is None and room_type is RoomType.HARD:
                new_id = self.attach(self.spine[-1], RoomType.NORMAL, prefer_drift=True)
            if new_id is None:
                return False
            self.spine.append(new_id)
        boss_id = self.attach(self.spine[-1], RoomType.BOSS, prefer_drift=True)
        if boss_id is None:
            return False
        self.spine.append(boss_id)
        return True

    def attach_stairs(self, boss_id: RoomId) -> Optional[RoomId]:
        """Лестница висит на боссе и больше ни на ком (ГДД 3.2)."""
        return self.attach(boss_id, RoomType.STAIRS)

    def grow_branches(self, target_rooms: int) -> None:
        cfg = self.cfg
        blocked: Set[RoomId] = set()
        while len(self.rooms) < target_rooms:
            anchors = [
                rid for rid, room in self.rooms.items()
                if room.type not in PROTECTED_TYPES and rid not in blocked
            ]
            if not anchors:
                break
            anchor = self.rng.choice(sorted(anchors))
            chain = self.rng.randint(*cfg.branch_length)
            terminal = self._next_terminal()
            cur, grown, placed_terminal = anchor, [], False
            for step in range(chain):
                if len(self.rooms) >= target_rooms:
                    break
                last = step == chain - 1
                want = terminal if last else RoomType.NORMAL
                new_id = self.attach(cur, want)
                if new_id is None and last:
                    new_id = self.attach(cur, RoomType.NORMAL)  # терминал не влез
                elif new_id is not None and last:
                    placed_terminal = want is terminal
                if new_id is None:
                    break
                grown.append(new_id)
                cur = new_id
            if terminal not in (RoomType.NORMAL, None) and not placed_terminal:
                self.terminal_queue.append(terminal)   # вернём в очередь
            if not grown:
                blocked.add(anchor)

    def _next_terminal(self) -> RoomType:
        """Чем закончить тупик: сперва обязательные типы, потом ГДД 40/30/30."""
        while self.terminal_queue:
            wanted = self.terminal_queue.pop()
            if self.can_place(wanted):
                return wanted
        wanted = _pick_weighted(self.rng, list(self.cfg.branch_terminal_weights))
        return wanted if self.can_place(wanted) else RoomType.NORMAL

    def _retype(self, rid: RoomId, room_type: RoomType) -> None:
        old = self.rooms[rid].type
        self.counts[old] = self.counts.get(old, 1) - 1
        self.rooms[rid] = self.rooms[rid].retyped(room_type)
        self.counts[room_type] = self.counts.get(room_type, 0) + 1

    def _degree(self, rid: RoomId) -> int:
        return sum(1 for d in self.corridors if rid in d)

    def add_loops(self, boss_id: RoomId) -> None:
        """Лишние связи между уже стоящими комнатами — развилки из ГДД 3.3.

        Петля принимается, только если она не укорачивает маршрут до босса:
        обязательные 5–6 комнат должны остаться обязательными.
        """
        cfg = self.cfg
        loopable = {RoomType.SPAWN, RoomType.NORMAL, RoomType.HARD}
        base_dist = self._distance(self.spine[0], boss_id)
        ids = sorted(self.rooms)
        for i, a_id in enumerate(ids):
            if self.rooms[a_id].type not in loopable:
                continue
            for b_id in ids[i + 1:]:
                if self.rooms[b_id].type not in loopable:
                    continue
                if frozenset((a_id, b_id)) in self.corridors:
                    continue
                if self.rng.random() >= cfg.loop_chance:
                    continue
                corridor = self._between(self.rooms[a_id], self.rooms[b_id])
                if corridor is None or not self._fits_corridor(corridor):
                    continue
                self.corridors[frozenset((a_id, b_id))] = corridor
                if self._distance(self.spine[0], boss_id) < base_dist:
                    del self.corridors[frozenset((a_id, b_id))]

    def _between(self, a: Room, b: Room) -> Optional[Corridor]:
        """Прямая перемычка между двумя комнатами, если они смотрят друг на друга."""
        cfg = self.cfg
        width = cfg.corridor_width
        lo, hi = cfg.loop_corridor_length
        if a.x2 <= b.x or b.x2 <= a.x:                       # разнесены по X
            left, right = (a, b) if a.x2 <= b.x else (b, a)
            gap = right.x - left.x2
            if not lo <= gap <= hi:
                return None
            o0, o1 = max(a.y, b.y) + 1, min(a.y2, b.y2) - 1
            if o1 - o0 < width:
                return None
            y = (o0 + o1 - width) // 2
            return Corridor(left.id, right.id, "h", left.x2, y, gap, width)
        if a.y2 <= b.y or b.y2 <= a.y:                       # разнесены по Y
            top, bottom = (a, b) if a.y2 <= b.y else (b, a)
            gap = bottom.y - top.y2
            if not lo <= gap <= hi:
                return None
            o0, o1 = max(a.x, b.x) + 1, min(a.x2, b.x2) - 1
            if o1 - o0 < width:
                return None
            x = (o0 + o1 - width) // 2
            return Corridor(top.id, bottom.id, "v", x, top.y2, width, gap)
        return None

    def _fits_corridor(self, corridor: Corridor) -> bool:
        for room in self.rooms.values():
            if room.id not in (corridor.a, corridor.b) and corridor.hits(room, 1):
                return False
        for existing in self.corridors.values():
            if _boxes_touch(corridor, existing, 1):
                return False
        return True

    def _distance(self, src: RoomId, dst: RoomId) -> int:
        dist = {src: 0}
        q = deque([src])
        while q:
            cur = q.popleft()
            if cur == dst:
                return dist[cur]
            for door in self.corridors:
                if cur not in door:
                    continue
                nxt = next(iter(door - {cur}))
                if nxt not in dist:
                    dist[nxt] = dist[cur] + 1
                    q.append(nxt)
        return 10 ** 6

    def normalise(self) -> Tuple[int, int]:
        """Сдвинуть этаж в положительные координаты и вернуть его размер."""
        pad = self.cfg.room_margin
        min_x = min(r.x for r in self.rooms.values()) - pad
        min_y = min(r.y for r in self.rooms.values()) - pad
        self.rooms = {rid: room.moved(-min_x, -min_y) for rid, room in self.rooms.items()}
        self.corridors = {k: c.moved(-min_x, -min_y) for k, c in self.corridors.items()}
        width = max(r.x2 for r in self.rooms.values()) + pad
        height = max(r.y2 for r in self.rooms.values()) + pad
        return width, height

    # --- сборка -----------------------------------------------------------
    def build(self) -> Optional[Floor]:
        self.plan_specials()
        spawn_id = self.seed_spawn()
        if not self.grow_spine():
            return None
        boss_id = self.spine[-1]
        stairs_id = self.attach_stairs(boss_id)
        if stairs_id is None:
            return None
        lo, hi = self.cfg.total_rooms
        target = int(round(self.rng.triangular(lo, hi, self.cfg.total_rooms_peak)))
        self.grow_branches(target)
        self.add_loops(boss_id)
        width, height = self.normalise()
        return Floor(
            rooms_by_id=dict(self.rooms),
            corridors=dict(self.corridors),
            spine=list(self.spine),
            spawn=spawn_id,
            boss=boss_id,
            stairs=stairs_id,
            seed=-1,
            attempts=0,
            config=self.cfg,
            width=width,
            height=height,
        )


def _boxes_touch(a, b, margin: int) -> bool:
    return not (
        a.x2 + margin <= b.x or b.x2 + margin <= a.x
        or a.y2 + margin <= b.y or b.y2 + margin <= a.y
    )


# ---------------------------------------------------------------------------
# Публичный вход
# ---------------------------------------------------------------------------

def generate(seed: int, cfg: Optional[GenConfig] = None) -> Floor:
    """Сгенерировать этаж. Проверки — внутри цикла попыток."""
    from .validation import validate

    cfg = cfg or GenConfig()
    for attempt in range(cfg.max_attempts):
        rng = random.Random((seed * 1_000_003 + attempt) & 0xFFFF_FFFF)
        floor = _Builder(cfg, rng).build()
        if floor is None:
            continue
        floor.seed = seed
        floor.attempts = attempt + 1
        if not validate(floor):
            return floor
    raise GenerationError(
        f"не удалось собрать корректный этаж за {cfg.max_attempts} попыток (seed={seed})"
    )
