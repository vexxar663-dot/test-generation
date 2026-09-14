"""Тесты генератора этажа. Только stdlib: `python3 -m unittest discover -s tests`."""

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
    """Инварианты, которые должны держаться на любом сиде (шаг 8 ГДД)."""

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
            self.assertEqual(a.grid, b.grid)
            self.assertEqual(a.doors, b.doors)
            self.assertEqual(a.main_path, b.main_path)

    def test_anchors_fixed(self):
        for floor in self.floors:
            self.assertIs(floor.type_at(self.cfg.spawn), RoomType.SPAWN)
            self.assertIs(floor.type_at(self.cfg.boss), RoomType.BOSS)
            self.assertIn(floor.stairs, self.cfg.stairs_candidates)

    def test_stairs_only_behind_boss(self):
        """Ключевое игровое правило: на следующий этаж — только через боссфайт."""
        for floor in self.floors:
            with self.subTest(seed=floor.seed):
                self.assertEqual(floor.linked(floor.stairs), [self.cfg.boss])
                # Убрать босса — и лестница становится недостижимой.
                reachable = {self.cfg.spawn}
                stack = [self.cfg.spawn]
                while stack:
                    cur = stack.pop()
                    for nxt in floor.linked(cur):
                        if nxt != self.cfg.boss and nxt not in reachable:
                            reachable.add(nxt)
                            stack.append(nxt)
                self.assertNotIn(floor.stairs, reachable)

    def test_every_room_reachable(self):
        for floor in self.floors:
            with self.subTest(seed=floor.seed):
                dist = floor.distances_from_spawn()
                self.assertEqual(set(dist), set(floor.rooms()))

    def test_terminal_rooms_are_dead_ends(self):
        for floor in self.floors:
            for cell, room_type in floor.grid.items():
                if room_type in TERMINAL_TYPES:
                    with self.subTest(seed=floor.seed, cell=cell):
                        self.assertEqual(floor.degree(cell), 1)

    def test_room_counts_within_gdd_limits(self):
        lo, hi = self.cfg.total_rooms
        for floor in self.floors:
            with self.subTest(seed=floor.seed):
                self.assertTrue(lo <= len(floor.rooms()) <= hi)
                counts = floor.counts()
                for room_type, (cap_lo, cap_hi) in self.cfg.caps.items():
                    self.assertTrue(cap_lo <= counts.get(room_type, 0) <= cap_hi,
                                    f"{room_type} = {counts.get(room_type, 0)}")

    def test_doors_connect_orthogonal_rooms_only(self):
        for floor in self.floors:
            for door in floor.doors:
                a, b = tuple(door)
                self.assertEqual(abs(a[0] - b[0]) + abs(a[1] - b[1]), 1)
                self.assertTrue(floor.type_at(a).is_room and floor.type_at(b).is_room)

    def test_main_path_length_respects_geometry(self):
        allowed = {n for n, _ in self.cfg.main_path_lengths}
        for floor in self.floors:
            self.assertIn(len(floor.main_path), allowed)
            # Путь короче манхэттенского расстояния невозможен.
            self.assertGreaterEqual(len(floor.main_path) - 1, 8)

    def test_no_room_without_exit(self):
        for floor in self.floors:
            for cell in floor.rooms():
                self.assertGreaterEqual(floor.degree(cell), 1)


class TestDistributions(unittest.TestCase):
    """Частоты из ГДД 3.2/3.4 — допуск ±6 п.п. на 1000 сидах."""

    @classmethod
    def setUpClass(cls):
        cls.floors = [generate(s) for s in range(1000)]

    def _share(self, room_type) -> float:
        """Доля этажей, на которых встречается хотя бы одна такая комната."""
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


class TestConfigurable(unittest.TestCase):
    """Алгоритм не зашит в 5×5 — те же шаги работают на другой сетке."""

    def test_six_by_six_floor(self):
        cfg = GenConfig(
            height=6, width=6, boss=(5, 5),
            stairs_candidates=((5, 4), (4, 5)),
            main_path_lengths=((11, 0.5), (13, 0.35), (15, 0.15)),
            total_rooms=(24, 30), total_rooms_peak=27.0,
            caps={
                RoomType.SPAWN: (1, 1), RoomType.BOSS: (1, 1), RoomType.STAIRS: (1, 1),
                RoomType.NORMAL: (8, 20), RoomType.HARD: (1, 3),
                RoomType.CAFETERIA: (0, 1), RoomType.TOILET: (0, 1),
                RoomType.CHEST: (1, 3), RoomType.EVENT: (0, 2),
            },
        )
        for seed in range(60):
            floor = generate(seed, cfg)
            with self.subTest(seed=seed):
                self.assertEqual(validate(floor), [])
                self.assertTrue(24 <= len(floor.rooms()) <= 30)


if __name__ == "__main__":
    unittest.main(verbosity=2)
