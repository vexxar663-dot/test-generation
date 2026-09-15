"""Тесты школьной планировки на тайлах."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from roomgen import tilemap as T  # noqa: E402
from roomgen.config import GenConfig, RoomType  # noqa: E402
from roomgen.generator import generate  # noqa: E402

SEEDS = range(120)


class TestSchoolLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = GenConfig()
        cls.pairs = [(f, T.build(f)) for f in (generate(s, cls.cfg) for s in SEEDS)]

    def test_every_room_fits_its_block(self):
        for floor, tm in self.pairs:
            self.assertEqual(set(tm.room_rects), set(floor.rooms()))
            for cell, (rx, ry, rw, rh) in tm.room_rects.items():
                bx, by, bw, bh = T._block(cell)
                self.assertTrue(bx <= rx and rx + rw <= bx + bw)
                self.assertTrue(by <= ry and ry + rh <= by + bh)
                expected = T.ROOM_SIZES.get(floor.type_at(cell), (bw, bh))
                self.assertEqual((rw, rh), expected)

    def test_rooms_do_not_overlap(self):
        for _floor, tm in self.pairs:
            seen = set()
            for rx, ry, rw, rh in tm.room_rects.values():
                block = {(x, y) for y in range(ry, ry + rh) for x in range(rx, rx + rw)}
                self.assertFalse(block & seen)
                seen |= block

    def test_classroom_is_big_enough_for_a_class(self):
        """Кабинет должен быть кабинетом: ~8×6 м при тайле 0.41 м."""
        for floor, tm in self.pairs:
            for cell in floor.rooms():
                if floor.type_at(cell) in T.ROOM_SIZES:
                    continue  # толчок, сундук и лестница — намеренно меньше
                _rx, _ry, rw, rh = tm.room_rects[cell]
                self.assertGreaterEqual((rw - 2) * (rh - 2), 280)

    def test_all_rooms_reachable_over_tiles(self):
        for floor, tm in self.pairs:
            with self.subTest(seed=floor.seed):
                reach = tm.walkable_from(tm.room_center(self.cfg.spawn))
                for cell in floor.rooms():
                    self.assertIn(tm.room_center(cell), reach, f"комната {cell}")

    def test_no_orphan_corridors(self):
        """Коридора, в который нельзя попасть, на карте быть не должно."""
        for floor, tm in self.pairs:
            reach = tm.walkable_from(tm.room_center(self.cfg.spawn))
            orphans = [
                (x, y)
                for y in range(tm.height) for x in range(tm.width)
                if tm.tiles[y][x] in T.WALKABLE and (x, y) not in reach
            ]
            self.assertEqual(orphans, [], f"seed {floor.seed}")

    def test_stairs_only_behind_boss(self):
        """Ключевое правило ГДД, проверенное на тайлах, а не на графе."""
        for floor, tm in self.pairs:
            bx, by, bw, bh = tm.room_rects[self.cfg.boss]
            boss_block = {(x, y) for y in range(by, by + bh) for x in range(bx, bx + bw)}
            start = tm.room_center(self.cfg.spawn)
            seen, stack = {start}, [start]
            while stack:
                x, y = stack.pop()
                for nxt in ((x+1, y), (x-1, y), (x, y+1), (x, y-1)):
                    if nxt in seen or nxt in boss_block:
                        continue
                    if tm.at(*nxt) in T.WALKABLE:
                        seen.add(nxt)
                        stack.append(nxt)
            with self.subTest(seed=floor.seed):
                self.assertNotIn(tm.room_center(floor.stairs), seen)

    def test_stairs_vestibule_is_private(self):
        """Из лестницы, не заходя к боссу, нельзя попасть ни в одну другую комнату."""
        for floor, tm in self.pairs:
            bx, by, bw, bh = tm.room_rects[self.cfg.boss]
            boss_block = {(x, y) for y in range(by, by + bh) for x in range(bx, bx + bw)}
            start = tm.room_center(floor.stairs)
            seen, stack = {start}, [start]
            while stack:
                x, y = stack.pop()
                for nxt in ((x+1, y), (x-1, y), (x, y+1), (x, y-1)):
                    if nxt in seen or nxt in boss_block:
                        continue
                    if tm.at(*nxt) in T.WALKABLE:
                        seen.add(nxt)
                        stack.append(nxt)
            others = {tm.owner[xy] for xy in seen if xy in tm.owner} - {floor.stairs}
            with self.subTest(seed=floor.seed):
                self.assertEqual(others, set(), "тамбур лестницы ведёт наружу")

    def test_every_room_has_a_way_in(self):
        for floor, tm in self.pairs:
            for cell in floor.rooms():
                rx, ry, rw, rh = tm.room_rects[cell]
                ring = [(x, y)
                        for y in range(ry, ry + rh) for x in range(rx, rx + rw)
                        if x in (rx, rx + rw - 1) or y in (ry, ry + rh - 1)]
                doors = sum(1 for xy in ring if tm.at(*xy) is T.Tile.DOORWAY)
                self.assertGreater(doors, 0, f"seed {floor.seed}, комната {cell}")

    def test_hallways_serve_several_rooms(self):
        """Школа, а не цепочка: хотя бы один коридор обслуживает 3+ кабинета."""
        for floor, tm in self.pairs:
            best = 0
            for hall_r, (x0, x1) in tm.halls.items():
                y0, _y1 = T._hall_band(hall_r)
                served = {
                    tm.owner[(tx, ty)]
                    for ty in (y0 - 1, y0 + T.HALL)
                    for tx in range(x0, x1)
                    if tm.at(tx, ty) is T.Tile.DOORWAY and (tx, ty) in tm.owner
                }
                best = max(best, len(served))
            self.assertGreaterEqual(best, 3, f"seed {floor.seed}: коридоры не школьные")

    def test_forced_rooms_match_gdd_main_path(self):
        """ГДД 3.1: «основной путь спавн → босс — 5–6 комнат»."""
        counts = [T.rooms_to_boss(f, tm) for f, tm in self.pairs]
        rooms_on_route = [c + 1 for c in counts]  # плюс сам спавн
        mean = sum(rooms_on_route) / len(rooms_on_route)
        self.assertTrue(5.0 <= mean <= 6.0, f"среднее {mean:.2f} вне 5–6")
        self.assertGreaterEqual(min(rooms_on_route), 3)

    def test_props_have_room_to_stand(self):
        for floor, tm in self.pairs:
            for cell in floor.rooms():
                self.assertGreaterEqual(len(tm.interior(cell)), 60)

    def test_export_is_json_serialisable(self):
        import json

        floor, tm = self.pairs[0]
        data = json.loads(json.dumps(T.to_dict(floor, tm), ensure_ascii=False))
        self.assertEqual(len(data["rooms"]), len(floor.rooms()))
        self.assertEqual(len(data["tiles"]["rows"]), tm.height)
        self.assertTrue(all(len(r) == tm.width for r in data["tiles"]["rows"]))
        self.assertEqual(data["tiles"]["room_block"], [T.ROOM_W, T.ROOM_H])


class TestAtlas(unittest.TestCase):
    def test_all_named_sprites_load(self):
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            self.skipTest("нет Pillow")
        from roomgen.sprites import ENEMIES, FLOOR_FAMILIES, PROPS, WALL_BRICK, Atlas

        atlas = Atlas()
        for key in PROPS:
            self.assertIsNotNone(atlas.prop(key).getbbox(), f"{key}: вырезка пустая")
        for key in ENEMIES:
            self.assertIsNotNone(atlas.enemy(key).getbbox(), key)
        self.assertIsNotNone(atlas.hero().getbbox())
        for family in FLOOR_FAMILIES:
            self.assertEqual(atlas.floor_tile(family, 0).size, (16, 16))
        for brick in WALL_BRICK:
            self.assertEqual(atlas.wall_tile(brick).size, (16, 16))

    def test_every_room_type_has_a_theme(self):
        for room_type in RoomType:
            if room_type is not RoomType.EMPTY:
                self.assertIn(room_type, T.THEME)


if __name__ == "__main__":
    unittest.main(verbosity=2)
