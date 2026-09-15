"""Конфигурация генератора этажа «Equation Dodge».

Планировка свободная: комнаты — прямоугольники разного размера, стоящие в
общем поле координат и соединённые короткими прямыми перемычками. Никакой
сетки нет; форма этажа получается из порядка роста, а не из ячеек.

Размеры комнат заданы в тайлах. Масштаб выведен из спрайтов проекта: дверь
из `walls/floor_walls.png` — 35×60 px при реальных 0.9×2.05 м, значит
тайл 16 px ≈ 0.41 м. Поэтому кабинет 20×15 тайлов — это 8.2×6.2 м.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Tuple

RoomId = int
Size = Tuple[int, int]

#: Метров в одном тайле — из масштаба спрайтов.
METERS_PER_TILE = 0.41

#: Скорость бега героя, м/с. Предположение: нужна, чтобы оценить время на
#: пробежку по комнате — при больших залах оно перестаёт быть пренебрежимым.
PLAYER_SPEED_MPS = 4.0


class RoomType(Enum):
    """Типы комнат из ГДД 3.2."""

    SPAWN = "spawn"
    NORMAL = "normal"
    HARD = "hard"            # усложнённая комната (рычаг выбора сложности)
    CAFETERIA = "cafeteria"  # столовая
    TOILET = "toilet"        # толчок
    CHEST = "chest"          # сундук
    EVENT = "event"          # ивентовая комната / головоломка
    BOSS = "boss"
    STAIRS = "stairs"        # лестничная площадка


RU_NAME: Dict[RoomType, str] = {
    RoomType.SPAWN: "Спавн",
    RoomType.NORMAL: "Комната",
    RoomType.HARD: "Усложнённая",
    RoomType.CAFETERIA: "Столовая",
    RoomType.TOILET: "Толчок",
    RoomType.CHEST: "Сундук",
    RoomType.EVENT: "Ивентовая",
    RoomType.BOSS: "Боссфайт",
    RoomType.STAIRS: "Лестничная площадка",
}

GLYPH: Dict[RoomType, str] = {
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
ROOM_SECONDS: Dict[RoomType, Tuple[int, int]] = {
    RoomType.SPAWN: (0, 0),
    RoomType.NORMAL: (5, 15),
    RoomType.HARD: (15, 30),
    RoomType.CAFETERIA: (10, 20),
    RoomType.TOILET: (5, 10),
    RoomType.CHEST: (5, 10),
    RoomType.EVENT: (15, 30),
    RoomType.BOSS: (30, 90),
    RoomType.STAIRS: (10, 20),  # предположение: выбор перка на площадке
}

#: Секунды на саму дверь (открыть, пройти проём). Дорога считается отдельно.
TRANSITION_SECONDS = 1.0

#: Комнаты-тупики: степень в графе всегда 1, к ним не пристраивают проходы.
TERMINAL_TYPES = frozenset(
    {RoomType.CHEST, RoomType.CAFETERIA, RoomType.TOILET, RoomType.EVENT}
)

#: К этим комнатам нельзя добавлять лишние связи.
PROTECTED_TYPES = frozenset({RoomType.BOSS, RoomType.STAIRS}) | TERMINAL_TYPES


@dataclass(frozen=True)
class GenConfig:
    """Параметры генерации. Всё, что в ГДД названо числом, вынесено сюда."""

    # --- состав этажа (ГДД 3.1–3.2) ---------------------------------------
    total_rooms: Tuple[int, int] = (16, 22)
    total_rooms_peak: float = 19.0
    #: Комнат на обязательном маршруте спавн → босс, включая обе (ГДД 3.1).
    spine_rooms: Tuple[int, int] = (5, 6)

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

    # --- размеры комнат в тайлах (ширина, высота), диапазоны ---------------
    #: Пропорции взяты с концепт-схемы: боссфайт крупнее обычной комнаты
    #: примерно вдвое по каждой стороне, столовая широкая, толчок узкий и
    #: вытянутый, спавн/сундук/лестница — маленькие.
    sizes: Dict[RoomType, Tuple[Size, Size]] = field(
        default_factory=lambda: {
            RoomType.SPAWN:     ((48, 60), (44, 52)),
            RoomType.NORMAL:    ((72, 96), (52, 68)),
            RoomType.HARD:      ((96, 120), (72, 92)),
            RoomType.CAFETERIA: ((120, 144), (64, 80)),
            RoomType.TOILET:    ((48, 60), (68, 88)),
            RoomType.CHEST:     ((48, 60), (44, 56)),
            RoomType.EVENT:     ((88, 108), (56, 72)),
            RoomType.BOSS:      ((128, 152), (104, 124)),
            RoomType.STAIRS:    ((52, 64), (44, 56)),
        }
    )

    # --- перемычки между комнатами ----------------------------------------
    #: Длина перемычки масштабирована вместе с комнатами, чтобы сохранились
    #: пропорции концепт-схемы: связь короткая относительно размера комнаты.
    corridor_length: Tuple[int, int] = (16, 40)
    #: Ширина оставлена вдвое меньше масштаба: 8 тайлов — это 3.3 м, ширина
    #: настоящего школьного коридора. При ×4 получилось бы 6.5 м, и проход
    #: перестал бы отличаться от комнаты.
    corridor_width: int = 8
    #: Минимальный зазор между стенами двух комнат (тайлов).
    room_margin: int = 12

    # --- ветвление ---------------------------------------------------------
    branch_length: Tuple[int, int] = (1, 3)
    branch_terminal_weights: Tuple[Tuple[RoomType, float], ...] = (
        (RoomType.CHEST, 0.40),
        (RoomType.CAFETERIA, 0.30),
        (RoomType.TOILET, 0.30),
    )
    hard_rooms: Tuple[int, int] = (1, 2)
    hard_dead_end_preference: float = 0.75
    event_chance: float = 0.50

    #: Шанс лишней связи между двумя уже стоящими комнатами (петли, ГДД 3.3).
    loop_chance: float = 0.45
    #: Для петель зазор допускается шире: комнаты вставали независимо друг
    #: от друга, и ровно 4–10 тайлов между ними попадается редко.
    loop_corridor_length: Tuple[int, int] = (12, 80)

    # --- служебное ---------------------------------------------------------
    placement_tries: int = 48
    max_attempts: int = 64
