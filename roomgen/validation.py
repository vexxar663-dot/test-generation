"""Шаг 8 ГДД — проверка корректности этажа.

validate() возвращает список нарушений. Пустой список = этаж валиден.
Генератор вызывает её на каждой попытке: этаж с нарушениями не отдаётся наружу.
"""

from __future__ import annotations

from collections import deque
from typing import Dict, List, Set

from .config import Cell, GenConfig, RoomType

__all__ = ["validate"]


def _reachable(floor) -> Set[Cell]:
    start = floor.config.spawn
    seen = {start}
    q = deque([start])
    while q:
        cur = q.popleft()
        for nxt in floor.linked(cur):
            if nxt not in seen:
                seen.add(nxt)
                q.append(nxt)
    return seen


def validate(floor) -> List[str]:
    cfg: GenConfig = floor.config
    errors: List[str] = []
    rooms = set(floor.rooms())

    # 1. Якорные комнаты на местах.
    if floor.type_at(cfg.spawn) is not RoomType.SPAWN:
        errors.append("спавн не на своей ячейке")
    if floor.type_at(cfg.boss) is not RoomType.BOSS:
        errors.append("босс не на своей ячейке")
    if floor.type_at(floor.stairs) is not RoomType.STAIRS:
        errors.append("лестница не на своей ячейке")
    if floor.stairs not in list(cfg.stairs_candidates):
        errors.append(f"лестница в недопустимой ячейке {floor.stairs}")

    # 2. Двери — только между ортогональными соседями и только между комнатами.
    for door in floor.doors:
        a, b = tuple(door)
        if abs(a[0] - b[0]) + abs(a[1] - b[1]) != 1:
            errors.append(f"дверь не между соседями: {a}–{b}")
        if a not in rooms or b not in rooms:
            errors.append(f"дверь ведёт в пустую ячейку: {a}–{b}")

    # 3. Лестница доступна только через босса.
    stairs_links = floor.linked(floor.stairs)
    if stairs_links != [cfg.boss] and stairs_links != sorted([cfg.boss]):
        errors.append(f"лестница соединена не только с боссом: {stairs_links}")
    boss_links = [c for c in floor.linked(cfg.boss) if c != floor.stairs]
    if len(boss_links) != 1:
        errors.append(f"у босса должен быть ровно один вход, а их {len(boss_links)}")

    # 4. Связность: всё достижимо от спавна, путь до босса есть, островков нет.
    seen = _reachable(floor)
    if cfg.boss not in seen:
        errors.append("нет пути от спавна до босса")
    orphans = rooms - seen
    if orphans:
        errors.append(f"изолированные комнаты: {sorted(orphans)}")
    for cell in rooms:
        if floor.degree(cell) == 0:
            errors.append(f"комната без выходов: {cell}")

    # 5. Количество комнат и лимиты типов (ГДД 3.1 и 3.2).
    total = len(rooms)
    lo, hi = cfg.total_rooms
    if not lo <= total <= hi:
        errors.append(f"комнат на этаже {total}, требуется {lo}–{hi}")
    counts: Dict[RoomType, int] = floor.counts()
    for room_type, (cap_lo, cap_hi) in cfg.caps.items():
        n = counts.get(room_type, 0)
        if not cap_lo <= n <= cap_hi:
            errors.append(f"{room_type.value}: {n}, требуется {cap_lo}–{cap_hi}")

    # 6. Тупиковые награды остаются тупиками.
    from .config import TERMINAL_TYPES

    for cell, room_type in floor.grid.items():
        if room_type in TERMINAL_TYPES and floor.degree(cell) != 1:
            errors.append(f"{room_type.value} {cell} не тупик (степень {floor.degree(cell)})")

    # 7. Основной путь — настоящий путь по дверям от спавна до босса.
    path = floor.main_path
    if not path or path[0] != cfg.spawn or path[-1] != cfg.boss:
        errors.append("основной путь не соединяет спавн и босса")
    else:
        if len(set(path)) != len(path):
            errors.append("основной путь самопересекается")
        for a, b in zip(path, path[1:]):
            if frozenset((a, b)) not in floor.doors:
                errors.append(f"на основном пути нет двери {a}–{b}")

    return errors
