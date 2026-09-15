"""Тесты генератора свободной планировки. Только stdlib."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from roomgen.config import TERMINAL_TYPES, GenConfig, RoomType  # noqa: E402
from roomgen.generator import generate  # noqa: E402
from roomgen.validation import validate  # noqa: E402

SEEDS = range(400)


class TestInvariants(unittest.TestCase):
    """Инварианты, которые должны держаться на любом сиде."""

    @classmethod
    def setUpClass(cls):
        cls.cfg = GenConfig()
        cls.floors = [generate(s, cls.cfg) for s in SEEDS]

    def test_all_floors_valid(self):
        for floor in self.floors:
            with self.subTest(seed=floor.seed):
                self.assertEqual(validate(floor), [])

    def test_deterministic(self):
        for seed in (0, 7, 12, 99):
            a, b = generate(seed), generate(seed)
            self.assertEqual(a.rooms_by_id, b.rooms_by_id)
            self.assertEqual(a.corridors, b.corridors)
            self.assertEqual(a.spine, b.spine)

    def test_rooms_never_overlap(self):
        """Главное геометрическое правило свободной упаковки."""
        for floor in self.floors:
            ids = floor.rooms()
            for i, a_id in enumerate(ids):
                for b_id in ids[i + 1:]:
                    with self.subTest(seed=floor.seed, pair=(a_id, b_id)):
                        self.assertFalse(floor.room(a_id).overlaps(floor.room(b_id)))

    def test_room_sizes_match_their_type(self):
        for floor in self.floors:
            for rid in floor.rooms():
                room = floor.room(rid)
                (wlo, whi), (hlo, hhi) = self.cfg.sizes[room.type]
                with self.subTest(seed=floor.seed, rid=rid):
                    self.assertTrue(wlo <= room.w <= whi)
                    self.assertTrue(hlo <= room.h <= hhi)

    def test_boss_is_the_biggest_room(self):
        """Размер кодирует тип: боссфайт — самый большой зал на этаже."""
        for floor in self.floors:
            boss_area = floor.room(floor.boss).w * floor.room(floor.boss).h
            for rid in floor.rooms():
                if rid == floor.boss:
                    continue
                room = floor.room(rid)
                self.assertGreater(boss_area, room.w * room.h, f"seed {floor.seed}")

    def test_corridors_are_straight_and_clear(self):
        for floor in self.floors:
            for door, corridor in floor.corridors.items():
                with self.subTest(seed=floor.seed, door=sorted(door)):
                    self.assertIn(corridor.axis, ("h", "v"))
                    self.assertGreater(corridor.w, 0)
                    self.assertGreater(corridor.h, 0)
                    for rid in floor.rooms():
                        if rid not in door:
                            self.assertFalse(corridor.hits(floor.room(rid)))

    def test_stairs_only_behind_boss(self):
        """Ключевое игровое правило: на следующий этаж — только через боссфайт."""
        for floor in self.floors:
            with self.subTest(seed=floor.seed):
                self.assertEqual(floor.linked(floor.stairs), [floor.boss])
                reachable = {floor.spawn}
                stack = [floor.spawn]
                while stack:
                    cur = stack.pop()
                    for nxt in floor.linked(cur):
                        if nxt != floor.boss and nxt not in reachable:
                            reachable.add(nxt)
                            stack.append(nxt)
                self.assertNotIn(floor.stairs, reachable)

    def test_every_room_reachable(self):
        for floor in self.floors:
            with self.subTest(seed=floor.seed):
                self.assertEqual(set(floor.distances_from_spawn()), set(floor.rooms()))

    def test_terminal_rooms_are_dead_ends(self):
        for floor in self.floors:
            for rid in floor.rooms():
                if floor.type_at(rid) in TERMINAL_TYPES:
                    with self.subTest(seed=floor.seed, rid=rid):
                        self.assertEqual(floor.degree(rid), 1)

    def test_room_counts_within_gdd_limits(self):
        lo, hi = self.cfg.total_rooms
        for floor in self.floors:
            with self.subTest(seed=floor.seed):
                self.assertTrue(lo <= len(floor.rooms()) <= hi)
                counts = floor.counts()
                for room_type, (cap_lo, cap_hi) in self.cfg.caps.items():
                    self.assertTrue(cap_lo <= counts.get(room_type, 0) <= cap_hi,
                                    f"{room_type} = {counts.get(room_type, 0)}")

    def test_route_to_boss_matches_gdd(self):
        """ГДД 3.1: основной путь спавн → босс — 5–6 комнат."""
        lo, hi = self.cfg.spine_rooms
        for floor in self.floors:
            with self.subTest(seed=floor.seed):
                self.assertTrue(lo <= len(floor.critical_path()) <= hi)

    def test_loops_do_not_shorten_the_route(self):
        """Петли — развилки, а не срезки: обязательные комнаты остаются такими."""
        for floor in self.floors:
            tree_len = len(floor.spine)
            self.assertEqual(len(floor.critical_path()), tree_len, f"seed {floor.seed}")


class TestDistributions(unittest.TestCase):
    """Частоты из ГДД 3.2/3.4 — допуск ±6 п.п. на 1000 сидах."""

    @classmethod
    def setUpClass(cls):
        cls.floors = [generate(s) for s in range(1000)]

    def _share(self, room_type) -> float:
        hits = sum(1 for f in self.floors if f.counts().get(room_type, 0))
        return hits / len(self.floors)

    def test_event_room_about_half_of_floors(self):
        self.assertAlmostEqual(self._share(RoomType.EVENT), 0.50, delta=0.06)

    def test_chest_and_hard_room_on_every_floor(self):
        self.assertEqual(self._share(RoomType.CHEST), 1.0)
        self.assertEqual(self._share(RoomType.HARD), 1.0)

    def test_average_rooms_in_gdd_band(self):
        mean = sum(len(f.rooms()) for f in self.floors) / len(self.floors)
        self.assertTrue(18.0 <= mean <= 20.0, f"среднее {mean:.2f} вне 18–20")

    def test_most_floors_have_a_loop(self):
        """Концепт зациклен: у большинства этажей есть альтернативный маршрут."""
        looped = sum(1 for f in self.floors
                     if len(f.corridors) - len(f.rooms()) + 1 > 0)
        self.assertGreater(looped / len(self.floors), 0.5)


class TestConfigurable(unittest.TestCase):
    """Алгоритм не зашит в одни числа: меняем параметры — он продолжает работать."""

    def test_longer_route_and_bigger_floor(self):
        cfg = GenConfig(spine_rooms=(8, 10), total_rooms=(24, 30), total_rooms_peak=27.0,
                        caps={
                            RoomType.SPAWN: (1, 1), RoomType.BOSS: (1, 1),
                            RoomType.STAIRS: (1, 1), RoomType.NORMAL: (10, 22),
                            RoomType.HARD: (1, 3), RoomType.CAFETERIA: (0, 1),
                            RoomType.TOILET: (0, 1), RoomType.CHEST: (1, 3),
                            RoomType.EVENT: (0, 2),
                        })
        for seed in range(60):
            floor = generate(seed, cfg)
            with self.subTest(seed=seed):
                self.assertEqual(validate(floor), [])
                self.assertTrue(24 <= len(floor.rooms()) <= 30)
                self.assertTrue(8 <= len(floor.critical_path()) <= 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
