"""Генерация этажа «Equation Dodge» — 8 шагов из ГДД 3.4.

Алгоритм детерминирован по сиду: generate(seed) всегда даёт один и тот же этаж.
Зависимостей нет (только stdlib) — модуль переносится в GDScript один-в-один.

Модель связей: двери хранятся ЯВНО (set рёбер), а не выводятся из соседства.
Иначе шаг 7 («заполнить пустые ячейки») склеил бы тупики в коридоры и убил бы
всю схему «награда в конце тупика» из шага 4.
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
    Cell,
    GenConfig,
    RoomType,
)

Door = FrozenSet[Cell]


class GenerationError(RuntimeError):
    """Не удалось собрать корректный этаж за max_attempts попыток."""


@dataclass
class Floor:
    """Результат генерации: сетка типов + явный набор дверей."""

    grid: Dict[Cell, RoomType]
    doors: Set[Door]
    main_path: List[Cell]
    stairs: Cell
    seed: int
    attempts: int
    config: GenConfig
    branch_chance: float = 0.0

    # --- доступ -----------------------------------------------------------
    def type_at(self, cell: Cell) -> RoomType:
        return self.grid.get(cell, RoomType.EMPTY)

    def rooms(self) -> List[Cell]:
        return [c for c, t in self.grid.items() if t.is_room]

    def linked(self, cell: Cell) -> List[Cell]:
        out = []
        for door in self.doors:
            if cell in door:
                a, b = tuple(door)
                out.append(b if a == cell else a)
        return sorted(out)

    def degree(self, cell: Cell) -> int:
        return sum(1 for d in self.doors if cell in d)

    def is_dead_end(self, cell: Cell) -> bool:
        return self.degree(cell) == 1

    def counts(self) -> Dict[RoomType, int]:
        res: Dict[RoomType, int] = {}
        for t in self.grid.values():
            if t.is_room:
                res[t] = res.get(t, 0) + 1
        return res

    def distances_from_spawn(self) -> Dict[Cell, int]:
        start = self.config.spawn
        dist = {start: 0}
        q = deque([start])
        while q:
            cur = q.popleft()
            for nxt in self.linked(cur):
                if nxt not in dist:
                    dist[nxt] = dist[cur] + 1
                    q.append(nxt)
        return dist

    def critical_path(self) -> List[Cell]:
        """Кратчайший путь спавн → босс по дверям (то, что игрок обязан пройти)."""
        start, goal = self.config.spawn, self.config.boss
        prev: Dict[Cell, Optional[Cell]] = {start: None}
        q = deque([start])
        while q:
            cur = q.popleft()
            if cur == goal:
                break
            for nxt in self.linked(cur):
                if nxt not in prev:
                    prev[nxt] = cur
                    q.append(nxt)
        if goal not in prev:
            return []
        path, node = [], goal
        while node is not None:
            path.append(node)
            node = prev[node]
        return list(reversed(path))

    # --- тайминг (ГДД «Тайминг прохождения этажа») ------------------------
    def time_estimate(self, cells: Optional[Sequence[Cell]] = None) -> Tuple[float, float]:
        """(мин, макс) секунд на список комнат; по умолчанию — весь этаж на 100%."""
        cells = list(self.rooms()) if cells is None else list(cells)
        lo = hi = 0.0
        for cell in cells:
            a, b = ROOM_SECONDS[self.type_at(cell)]
            lo += a
            hi += b
        moves = max(len(cells) - 1, 0)
        return lo + moves * TRANSITION_SECONDS, hi + moves * TRANSITION_SECONDS


# ---------------------------------------------------------------------------
# Вспомогательное
# ---------------------------------------------------------------------------

def _manhattan(a: Cell, b: Cell) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _weighted_shuffle(rng: random.Random, items: Sequence, weights: Sequence[float]) -> List:
    """Перемешивание без возврата пропорционально весам (ключи Эфраимидиса)."""
    keyed = []
    for item, w in zip(items, weights):
        w = max(w, 1e-9)
        keyed.append((rng.random() ** (1.0 / w), item))
    keyed.sort(key=lambda kv: kv[0], reverse=True)
    return [item for _, item in keyed]


def _pick_weighted(rng: random.Random, pairs: Sequence[Tuple]) -> object:
    total = sum(w for _, w in pairs)
    roll = rng.random() * total
    upto = 0.0
    for value, w in pairs:
        upto += w
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
        self.grid: Dict[Cell, RoomType] = {
            (r, c): RoomType.EMPTY for r in range(cfg.height) for c in range(cfg.width)
        }
        self.doors: Set[Door] = set()
        self.counts: Dict[RoomType, int] = {}
        self.main_path: List[Cell] = []
        self.stairs: Cell = cfg.stairs_candidates[0]
        self.branch_chance = 0.0

    # --- примитивы --------------------------------------------------------
    def cap_of(self, t: RoomType) -> int:
        return self.cfg.caps.get(t, (0, 10 ** 6))[1]

    def can_place(self, t: RoomType) -> bool:
        return self.counts.get(t, 0) < self.cap_of(t)

    def place(self, cell: Cell, t: RoomType) -> bool:
        """Поставить комнату с учётом лимита типа. False — лимит исчерпан."""
        if not self.can_place(t):
            return False
        old = self.grid[cell]
        if old.is_room:
            self.counts[old] -= 1
        self.grid[cell] = t
        self.counts[t] = self.counts.get(t, 0) + 1
        return True

    def retype(self, cell: Cell, t: RoomType) -> bool:
        return self.place(cell, t)

    def connect(self, a: Cell, b: Cell) -> None:
        assert _manhattan(a, b) == 1, "дверь только между ортогональными соседями"
        self.doors.add(frozenset((a, b)))

    def is_free(self, cell: Cell) -> bool:
        return self.grid[cell] is RoomType.EMPTY

    def occupied_neighbors(self, cell: Cell) -> List[Cell]:
        return [n for n in self.cfg.neighbors(cell) if not self.is_free(n)]

    def room_count(self) -> int:
        return sum(1 for t in self.grid.values() if t.is_room)

    # --- Шаг 2: якорные комнаты ------------------------------------------
    def step2_anchors(self) -> None:
        cfg = self.cfg
        self.place(cfg.spawn, RoomType.SPAWN)
        self.place(cfg.boss, RoomType.BOSS)
        self.stairs = self.rng.choice(list(cfg.stairs_candidates))
        self.place(self.stairs, RoomType.STAIRS)
        # Лестница соединена ТОЛЬКО с боссом: пройти на следующий этаж
        # можно лишь через боссфайт (ГДД 3.2 «всегда после босса»).
        self.connect(self.stairs, cfg.boss)

    # --- Шаг 3: основной путь --------------------------------------------
    def step3_main_path(self) -> bool:
        cfg = self.cfg
        start, goal = cfg.spawn, cfg.boss
        base = _manhattan(start, goal)
        lengths = [
            (n, w)
            for n, w in cfg.main_path_lengths
            if (n - 1) >= base and (n - 1 - base) % 2 == 0
        ]
        if not lengths:
            return False
        order: List[int] = []
        pool = list(lengths)
        while pool:
            chosen = _pick_weighted(self.rng, pool)
            order.append(chosen)
            pool = [p for p in pool if p[0] != chosen]

        for target in order:
            path = self._search_path(start, goal, target)
            if path:
                self.main_path = path
                for cell in path[1:-1]:
                    if not self.place(cell, RoomType.NORMAL):
                        return False
                for a, b in zip(path, path[1:]):
                    self.connect(a, b)
                return True
        return False

    def _search_path(self, start: Cell, goal: Cell, target_cells: int) -> Optional[List[Cell]]:
        """Самонепересекающийся случайный путь ровно из target_cells клеток.

        Обход в глубину с откатом; ветки, из которых до босса уже не дойти
        за оставшийся бюджет шагов (или не сойдётся чётность), отсекаются —
        поэтому «перезапуск генерации» из ГДД здесь почти никогда не нужен.
        """
        cfg = self.cfg
        blocked = {self.stairs}
        path: List[Cell] = [start]
        visited: Set[Cell] = {start}

        def rec() -> bool:
            cur = path[-1]
            if cur == goal:
                return len(path) == target_cells
            moves_left = target_cells - len(path)
            if moves_left <= 0:
                return False
            cands = [
                n for n in cfg.neighbors(cur)
                if n not in visited and n not in blocked and (self.is_free(n) or n == goal)
            ]
            weights = [
                cfg.toward_boss_weight if _manhattan(n, goal) < _manhattan(cur, goal) else 1.0
                for n in cands
            ]
            for nxt in _weighted_shuffle(self.rng, cands, weights):
                rest = moves_left - 1
                dist = _manhattan(nxt, goal)
                if dist > rest or (rest - dist) % 2 != 0:
                    continue  # отсечение: не дойти или не сойдётся чётность
                if nxt == goal and rest != 0:
                    continue  # пришли к боссу раньше запланированной длины
                path.append(nxt)
                visited.add(nxt)
                if rec():
                    return True
                path.pop()
                visited.discard(nxt)
            return False

        return list(path) if rec() else None

    # --- Шаг 4: ответвления-тупики ---------------------------------------
    def step4_branches(self) -> None:
        cfg = self.cfg
        lo, hi = cfg.branch_chance
        self.branch_chance = self.rng.uniform(lo, hi)
        # Спавн и босс из ГДД исключены; лестница — тоже (она только за боссом).
        anchors = [c for c in self.main_path[1:-1]]
        self.rng.shuffle(anchors)
        for anchor in anchors:
            if self.rng.random() >= self.branch_chance:
                continue
            self._grow_branch(anchor)

    def _growable(self, cell: Cell, parent: Cell) -> bool:
        """Клетка годится для тупика, если она пуста.

        Двери хранятся явно, поэтому физическое соседство с чужой комнатой не
        создаёт прохода: цепочка остаётся деревом, даже если вьётся вплотную
        к основному пути. Требование «единственный занятый сосед» отсекало бы
        ~60% ответвлений на извилистых путях.
        """
        del parent  # соседство больше не ограничивает рост
        return self.is_free(cell)

    def _grow_branch(self, anchor: Cell) -> None:
        cfg = self.cfg
        length = self.rng.randint(*cfg.branch_length)
        chain: List[Cell] = []
        cur = anchor
        for _ in range(length):
            options = [n for n in cfg.neighbors(cur) if self._growable(n, cur)]
            if not options:
                break
            nxt = self.rng.choice(options)
            if not self.place(nxt, RoomType.NORMAL):
                break  # упёрлись в лимит обычных комнат
            self.connect(cur, nxt)
            chain.append(nxt)
            cur = nxt
        if not chain:
            return
        # Крайняя комната тупика получает специальный тип (ГДД: 40/30/30).
        terminal = chain[-1]
        wanted = _pick_weighted(self.rng, list(cfg.branch_terminal_weights))
        if self.can_place(wanted):
            self.retype(terminal, wanted)
        # иначе остаётся обычной — ровно как требует ГДД, шаг 4.

    # --- Шаг 5: усложнённые комнаты ---------------------------------------
    def step5_hard_rooms(self) -> None:
        cfg = self.cfg
        want = self.rng.randint(*cfg.hard_rooms)
        for _ in range(want):
            if not self.can_place(RoomType.HARD):
                break
            dead_ends, on_path = [], []
            for cell, t in self.grid.items():
                if t is not RoomType.NORMAL:
                    continue
                (dead_ends if self._degree(cell) == 1 else on_path).append(cell)
            pool = dead_ends
            if not pool or (on_path and self.rng.random() >= cfg.hard_dead_end_preference):
                pool = on_path or dead_ends
            if not pool:
                break
            self.retype(self.rng.choice(sorted(pool)), RoomType.HARD)

    def _degree(self, cell: Cell) -> int:
        return sum(1 for d in self.doors if cell in d)

    # --- Шаг 6: ивентовая комната -----------------------------------------
    def step6_event_room(self) -> None:
        if self.rng.random() >= self.cfg.event_chance:
            return
        on_path = set(self.main_path)
        pool = [
            cell for cell, t in self.grid.items()
            if t is RoomType.NORMAL and cell not in on_path and self._degree(cell) == 1
        ]
        if not pool:
            return
        self.retype(self.rng.choice(sorted(pool)), RoomType.EVENT)

    # --- Шаг 7: добор комнат + петли --------------------------------------
    def step7_fill(self, target: Optional[int] = None) -> None:
        cfg = self.cfg
        target = self._target_room_count() if target is None else target
        while self.room_count() < target:
            options: List[Tuple[Cell, List[Cell]]] = []
            for cell, t in self.grid.items():
                if t is not RoomType.EMPTY:
                    continue
                parents = [
                    n for n in self.occupied_neighbors(cell)
                    if self.grid[n] not in PROTECTED_TYPES
                ]
                if parents:
                    options.append((cell, parents))
            if not options:
                break  # присоединяться не к чему — ГДД: «остаются пустыми»
            cell, parents = self.rng.choice(sorted(options))
            if not self.place(cell, RoomType.NORMAL):
                break  # лимит обычных комнат исчерпан
            self.connect(cell, self.rng.choice(parents))

    def _target_room_count(self) -> int:
        """ГДД: 16–22, в среднем 18–20 — треугольное распределение, а не ровное."""
        lo, hi = self.cfg.total_rooms
        peak = self.cfg.total_rooms_peak
        return int(round(self.rng.triangular(lo, hi, peak)))

    def _add_loop_doors(self) -> None:
        """Развилки из ГДД 3.3: часть соседних комнат получает вторую дверь.

        Тупики и защищённые типы не участвуют, иначе «сундук в конце тупика»
        и правило «лестница только за боссом» перестают работать.
        """
        cfg = self.cfg
        loopable = {RoomType.SPAWN, RoomType.NORMAL, RoomType.HARD}
        for cell, t in sorted(self.grid.items()):
            if t not in loopable:
                continue
            for n in cfg.neighbors(cell):
                if n <= cell or self.grid[n] not in loopable:
                    continue
                if frozenset((cell, n)) in self.doors:
                    continue
                if self.rng.random() < cfg.loop_door_chance:
                    self.connect(cell, n)

    # --- Ремонт минимальных требований ------------------------------------
    def repair_minimums(self) -> None:
        """Дотягивает типы до нижних границ ГДД (напр. «сундук: 1–2»)."""
        for t, (lo, _hi) in self.cfg.caps.items():
            while self.counts.get(t, 0) < lo:
                cell = self._best_candidate_for(t)
                if cell is None:
                    return
                self.retype(cell, t)

    def _best_candidate_for(self, t: RoomType) -> Optional[Cell]:
        on_path = set(self.main_path)
        normals = [c for c, g in self.grid.items() if g is RoomType.NORMAL]
        if t in TERMINAL_TYPES:
            pool = [c for c in normals if self._degree(c) == 1 and c not in on_path]
            pool = pool or [c for c in normals if self._degree(c) == 1]
        else:
            pool = normals
        return self.rng.choice(sorted(pool)) if pool else None

    def build(self) -> Optional[Floor]:
        self.step2_anchors()
        if not self.step3_main_path():
            return None
        self.step4_branches()
        # ОТСТУПЛЕНИЕ ОТ ГДД: шаг 7 выполняется раньше шагов 5–6.
        # В порядке ГДД (4→5→6→7) к моменту выбора ивентовой комнаты тупиков
        # на этаже почти нет — все терминалы ответвлений уже стали сундуком/
        # столовой/толчком, — и ивент выпадал на ~1% этажей вместо 50%.
        # Набор шагов тот же, меняется только момент выбора типа.
        target = self._target_room_count()
        self.step7_fill(target)
        # ОТСТУПЛЕНИЕ ОТ ГДД: шаг 6 идёт перед шагом 5. Оба шага конвертируют
        # обычные комнаты, но у ивента требование жёстче («тупик вне основного
        # пути»), а усложнённой комнате тупик лишь «предпочтителен». В порядке
        # ГДД усложнённые комнаты выедали пул тупиков и ивент падал до ~24%
        # вместо заявленных 50%.
        self.step6_event_room()
        self.step5_hard_rooms()
        # Шаги 5–6 переводят обычные комнаты в усложнённые/ивентовые и тем
        # освобождают лимит «обычных» — добираем этаж до целевого размера.
        self.step7_fill(target)
        self.repair_minimums()
        # Развилки ставим последними, по финальной планировке.
        self._add_loop_doors()
        return Floor(
            grid=dict(self.grid),
            doors=set(self.doors),
            main_path=list(self.main_path),
            stairs=self.stairs,
            seed=-1,
            attempts=0,
            config=self.cfg,
            branch_chance=self.branch_chance,
        )


# ---------------------------------------------------------------------------
# Публичный вход
# ---------------------------------------------------------------------------

def generate(seed: int, cfg: Optional[GenConfig] = None) -> Floor:
    """Сгенерировать этаж. Шаг 8 (проверка связности) — внутри цикла попыток."""
    from .validation import validate  # локальный импорт: избегаем цикла

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
