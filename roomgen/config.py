"""Конфигурация генератора этажа «Equation Dodge».

Все числа взяты из ГДД (раздел 3 «Мир и этажи»). Места, где ГДД внутренне
противоречив или геометрически невыполним, помечены комментарием `ГДД-КОНФЛИКТ`
и описаны в docs/room_generation.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Tuple

Cell = Tuple[int, int]  # (row, col), row растёт вниз — как в ГДД: спавн (0,0), босс (4,4)


class RoomType(Enum):
    """Типы комнат из ГДД 3.2."""

    EMPTY = "empty"
    SPAWN = "spawn"
    NORMAL = "normal"
    HARD = "hard"          # усложнённая комната (рычаг выбора сложности)
    CAFETERIA = "cafeteria"  # столовая
    TOILET = "toilet"        # толчок
    CHEST = "chest"          # сундук
    EVENT = "event"          # ивентовая комната / головоломка
    BOSS = "boss"
    STAIRS = "stairs"        # лестничная площадка

    @property
    def is_room(self) -> bool:
        return self is not RoomType.EMPTY


#: Русские подписи для рендера.
RU_NAME: Dict[RoomType, str] = {
    RoomType.EMPTY: "пусто",
    RoomType.SPAWN: "Спавн",
    RoomType.NORMAL: "Обычная",
    RoomType.HARD: "Усложнённая",
    RoomType.CAFETERIA: "Столовая",
    RoomType.TOILET: "Толчок",
    RoomType.CHEST: "Сундук",
    RoomType.EVENT: "Ивент",
    RoomType.BOSS: "Босс",
    RoomType.STAIRS: "Лестница",
}

#: Односимвольные глифы — вторичное кодирование типа (не только цветом).
GLYPH: Dict[RoomType, str] = {
    RoomType.EMPTY: "",
    RoomType.SPAWN: "S",
    RoomType.NORMAL: "·",
    RoomType.HARD: "!",
    RoomType.CAFETERIA: "$",
    RoomType.TOILET: "W",
    RoomType.CHEST: "★",
    RoomType.EVENT: "?",
    RoomType.BOSS: "B",
    RoomType.STAIRS: "^",
}

#: Время прохождения комнаты в секундах (ГДД, «Тайминг прохождения этажа»).
#: STAIRS в таблице ГДД нет — там выбор перка на 3 стойках (ГДД 5.3), оценка наша.
ROOM_SECONDS: Dict[RoomType, Tuple[int, int]] = {
    RoomType.SPAWN: (0, 0),
    RoomType.NORMAL: (5, 15),
    RoomType.HARD: (15, 30),
    RoomType.CAFETERIA: (10, 20),
    RoomType.TOILET: (5, 10),
    RoomType.CHEST: (5, 10),
    RoomType.EVENT: (15, 30),
    RoomType.BOSS: (30, 90),
    RoomType.STAIRS: (10, 20),  # предположение: выбор перка на лестничной площадке
}

#: Секунды на переход между комнатами (дверь + пробежка). Предположение.
TRANSITION_SECONDS = 2.0

#: Комнаты-тупики: их степень в графе всегда равна 1, к ним нельзя пристроить
#: коридор или петлю — иначе «награда в конце тупика» перестаёт читаться.
TERMINAL_TYPES = frozenset(
    {RoomType.CHEST, RoomType.CAFETERIA, RoomType.TOILET, RoomType.EVENT}
)

#: Комнаты, к которым нельзя пристраивать новые двери на шаге 7/петлях.
#: Босс и лестница — жёсткое правило: лестницу нельзя достичь в обход босса.
PROTECTED_TYPES = frozenset({RoomType.BOSS, RoomType.STAIRS}) | TERMINAL_TYPES


@dataclass(frozen=True)
class GenConfig:
    """Параметры генерации. Всё, что в ГДД названо числом, вынесено сюда."""

    # --- Шаг 1: сетка -----------------------------------------------------
    height: int = 5
    width: int = 5

    # --- Шаг 2: якорные комнаты ------------------------------------------
    spawn: Cell = (0, 0)
    boss: Cell = (4, 4)
    #: Лестница ставится в одну из этих ячеек (ГДД: (4,3) или (3,4)).
    stairs_candidates: Tuple[Cell, ...] = ((4, 3), (3, 4))

    # --- Шаг 3: основной путь --------------------------------------------
    #: Длина основного пути в КЛЕТКАХ, включая спавн и босса, с весами выбора.
    #: ГДД-КОНФЛИКТ: ГДД просит «5–6 комнат» / «6–10 шагов», но манхэттенское
    #: расстояние (0,0)→(4,4) равно 8, поэтому короче 9 клеток пути не бывает,
    #: а чётность разрешает только нечётные длины: 9, 11, 13.
    #: Собственный пример ГДД («(0,0) → … → (4,4)») как раз 9 клеток.
    main_path_lengths: Tuple[Tuple[int, float], ...] = ((9, 0.55), (11, 0.35), (13, 0.10))
    #: Вес шага «в сторону босса» против «вбок/назад» — управляет извилистостью.
    toward_boss_weight: float = 3.0

    # --- Шаг 4: ответвления (тупики) --------------------------------------
    branch_chance: Tuple[float, float] = (0.40, 0.60)
    branch_length: Tuple[int, int] = (1, 3)
    #: Тип финальной комнаты тупика (ГДД: 40/30/30).
    branch_terminal_weights: Tuple[Tuple[RoomType, float], ...] = (
        (RoomType.CHEST, 0.40),
        (RoomType.CAFETERIA, 0.30),
        (RoomType.TOILET, 0.30),
    )

    # --- Шаг 5: усложнённые комнаты ---------------------------------------
    hard_rooms: Tuple[int, int] = (1, 2)
    #: С какой вероятностью усложнённая комната берётся из тупика, а не с пути.
    hard_dead_end_preference: float = 0.75

    # --- Шаг 6: ивентовая комната -----------------------------------------
    event_chance: float = 0.50

    # --- Шаг 7: добор комнат ----------------------------------------------
    total_rooms: Tuple[int, int] = (16, 22)
    #: Мода треугольного распределения числа комнат (ГДД: «в среднем 18–20»).
    total_rooms_peak: float = 19.0
    #: Шанс поставить дополнительную дверь между двумя соседними комнатами
    #: (развилки/петли из ГДД 3.3). Тупиковые и защищённые типы не участвуют.
    loop_door_chance: float = 0.12

    # --- Лимиты типов (ГДД 3.2), проверяются на шаге 8 ---------------------
    caps: Dict[RoomType, Tuple[int, int]] = field(
        default_factory=lambda: {
            RoomType.SPAWN: (1, 1),
            RoomType.BOSS: (1, 1),
            RoomType.STAIRS: (1, 1),
            RoomType.NORMAL: (6, 12),
            RoomType.HARD: (1, 2),
            RoomType.CAFETERIA: (0, 1),
            RoomType.TOILET: (0, 1),
            RoomType.CHEST: (1, 2),
            RoomType.EVENT: (0, 1),
        }
    )

    # --- Служебное --------------------------------------------------------
    max_attempts: int = 64

    def in_bounds(self, cell: Cell) -> bool:
        r, c = cell
        return 0 <= r < self.height and 0 <= c < self.width

    def neighbors(self, cell: Cell):
        """Соседи по горизонтали и вертикали (ГДД 3.3: без диагоналей)."""
        r, c = cell
        for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            if self.in_bounds((nr, nc)):
                yield (nr, nc)
