"""Проверка корректности этажа: геометрия, связность и лимиты ГДД.

validate() возвращает список нарушений. Пустой список = этаж валиден.
Генератор вызывает её на каждой попытке: этаж с нарушениями наружу не уходит.
"""

from __future__ import annotations

from collections import deque
from typing import Dict, List, Set

from .config import TERMINAL_TYPES, GenConfig, RoomId, RoomType

__all__ = ["validate"]


def _reachable(floor) -> Set[RoomId]:
    seen = {floor.spawn}
    q = deque([floor.spawn])
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
    rooms = floor.rooms_by_id

    # 1. Якорные комнаты на месте и в единственном экземпляре.
    if floor.type_at(floor.spawn) is not RoomType.SPAWN:
        errors.append("спавн потерял свой тип")
    if floor.type_at(floor.boss) is not RoomType.BOSS:
        errors.append("босс потерял свой тип")
    if floor.type_at(floor.stairs) is not RoomType.STAIRS:
        errors.append("лестница потеряла свой тип")

    # 2. Геометрия: комнаты не пересекаются, перемычки не режут чужие комнаты.
    ids = sorted(rooms)
    for i, a_id in enumerate(ids):
        for b_id in ids[i + 1:]:
            if rooms[a_id].overlaps(rooms[b_id]):
                errors.append(f"комнаты {a_id} и {b_id} пересекаются")
    for door, corridor in floor.corridors.items():
        for rid, room in rooms.items():
            if rid not in door and corridor.hits(room):
                errors.append(f"перемычка {sorted(door)} проходит сквозь комнату {rid}")
        if corridor.w <= 0 or corridor.h <= 0:
            errors.append(f"вырожденная перемычка {sorted(door)}")

    # 3. Лестница доступна только через комнату босса.
    if floor.linked(floor.stairs) != [floor.boss]:
        errors.append(f"лестница соединена не только с боссом: {floor.linked(floor.stairs)}")
    without_boss = {floor.spawn}
    stack = [floor.spawn]
    while stack:
        cur = stack.pop()
        for nxt in floor.linked(cur):
            if nxt == floor.boss or nxt in without_boss:
                continue
            without_boss.add(nxt)
            stack.append(nxt)
    if floor.stairs in without_boss:
        errors.append("на лестницу можно попасть мимо босса")

    # 4. Связность: всё достижимо от спавна, изолированных комнат нет.
    seen = _reachable(floor)
    if floor.boss not in seen:
        errors.append("нет пути от спавна до босса")
    orphans = set(rooms) - seen
    if orphans:
        errors.append(f"изолированные комнаты: {sorted(orphans)}")
    for rid in rooms:
        if floor.degree(rid) == 0:
            errors.append(f"комната без выходов: {rid}")

    # 5. Состав этажа (ГДД 3.1 и 3.2).
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
    for rid, room in rooms.items():
        if room.type in TERMINAL_TYPES and floor.degree(rid) != 1:
            errors.append(f"{room.type.value} {rid} не тупик (степень {floor.degree(rid)})")

    # 7. Обязательный маршрут до босса — ровно та длина, что просит ГДД 3.1.
    path = floor.critical_path()
    spine_lo, spine_hi = cfg.spine_rooms
    if not path:
        errors.append("маршрут до босса не найден")
    elif not spine_lo <= len(path) <= spine_hi:
        errors.append(f"до босса {len(path)} комнат, требуется {spine_lo}–{spine_hi}")

    return errors
