"""Тесты тайловой сетки и атласа спрайтов для свободной планировки."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from roomgen import tilemap as T  # noqa: E402
from roomgen.config import METERS_PER_TILE, GenConfig, RoomType  # noqa: E402
from roomgen.generator import generate  # noqa: E402

SEEDS = range(120)


class TestTileMap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = GenConfig()
        cls.pairs = [(f, T.build(f)) for f in (generate(s, cls.cfg) for s in SEEDS)]

    def test_tiles_match_generator_rects(self):
        for floor, tm in self.pairs:
            self.assertEqual(set(tm.room_rects), set(floor.rooms()))
            for rid, rect in tm.room_rects.items():
                room = floor.room(rid)
                self.assertEqual(rect, (room.x, room.y, room.w, room.h))

    def test_map_fits_its_declared_size(self):
        for floor, tm in self.pairs:
            self.assertEqual((tm.width, tm.height), (floor.width, floor.height))
            for rid in floor.rooms():
                room = floor.room(rid)
                self.assertTrue(0 <= room.x and room.x2 <= tm.width)
                self.assertTrue(0 <= room.y and room.y2 <= tm.height)

    def test_all_rooms_reachable_over_tiles(self):
        for floor, tm in self.pairs:
            with self.subTest(seed=floor.seed):
                reach = tm.walkable_from(tm.room_center(floor.spawn))
                for rid in floor.rooms():
                    self.assertIn(tm.room_center(rid), reach, f"комната {rid}")

    def test_no_orphan_corridors(self):
        """Прохода, в который нельзя попасть, на карте быть не должно."""
        for floor, tm in self.pairs:
            reach = tm.walkable_from(tm.room_center(floor.spawn))
            orphans = [
                (x, y)
                for y in range(tm.height) for x in range(tm.width)
                if tm.tiles[y][x] in T.WALKABLE and (x, y) not in reach
            ]
            self.assertEqual(orphans, [], f"seed {floor.seed}")

    def test_stairs_only_behind_boss_on_tiles(self):
        """То же правило ГДД, но проверенное на тайлах, а не на графе."""
        for floor, tm in self.pairs:
            bx, by, bw, bh = tm.room_rects[floor.boss]
            boss_block = {(x, y) for y in range(by, by + bh) for x in range(bx, bx + bw)}
            start = tm.room_center(floor.spawn)
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

    def test_every_room_has_a_doorway(self):
        for floor, tm in self.pairs:
            for rid in floor.rooms():
                x, y, w, h = tm.room_rects[rid]
                ring = [(tx, ty)
                        for ty in range(y, y + h) for tx in range(x, x + w)
                        if tx in (x, x + w - 1) or ty in (y, y + h - 1)]
                doors = sum(1 for xy in ring if tm.at(*xy) is T.Tile.DOORWAY)
                self.assertGreater(doors, 0, f"seed {floor.seed}, комната {rid}")

    def test_rooms_are_big_enough_for_gameplay(self):
        """Обычная комната — школьный класс, а не кладовка."""
        for floor, tm in self.pairs:
            for rid in floor.rooms():
                if floor.type_at(rid) is not RoomType.NORMAL:
                    continue
                _x, _y, w, h = tm.room_rects[rid]
                metres = (w - 2) * METERS_PER_TILE * (h - 2) * METERS_PER_TILE
                self.assertGreater(metres, 28.0, f"seed {floor.seed}: {metres:.0f} м²")

    def test_props_have_room_to_stand(self):
        for floor, tm in self.pairs:
            for rid in floor.rooms():
                self.assertGreaterEqual(len(tm.interior(rid)), 60)

    def test_rooms_to_boss_matches_the_graph(self):
        for floor, tm in self.pairs:
            self.assertEqual(T.rooms_to_boss(floor, tm), len(floor.critical_path()))

    def test_export_is_json_serialisable(self):
        import json

        floor, tm = self.pairs[0]
        data = json.loads(json.dumps(T.to_dict(floor, tm), ensure_ascii=False))
        self.assertEqual(len(data["rooms"]), len(floor.rooms()))
        self.assertEqual(len(data["corridors"]), len(floor.corridors))
        self.assertEqual(len(data["tiles"]["rows"]), tm.height)
        self.assertTrue(all(len(r) == tm.width for r in data["tiles"]["rows"]))
        self.assertEqual(data["size_tiles"], [floor.width, floor.height])


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
            self.assertIn(room_type, T.THEME)


if __name__ == "__main__":
    unittest.main(verbosity=2)
