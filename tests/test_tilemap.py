"""Тесты тайловой сетки: планировка на тайлах должна совпадать с графом комнат."""

from __future__ import annotations

import os
import sys
import unittest
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from roomgen import tilemap as T  # noqa: E402
from roomgen.config import GenConfig, RoomType  # noqa: E402
from roomgen.generator import generate  # noqa: E402

SEEDS = range(120)


class TestTileMap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = GenConfig()
        cls.pairs = [(f, T.build(f)) for f in (generate(s, cls.cfg) for s in SEEDS)]

    def test_every_room_has_a_block(self):
        for floor, tm in self.pairs:
            self.assertEqual(set(tm.room_rects), set(floor.rooms()))
            for _cell, (_x, _y, w, h) in tm.room_rects.items():
                self.assertEqual((w, h), (T.ROOM_W, T.ROOM_H))

    def test_rooms_do_not_overlap(self):
        for _floor, tm in self.pairs:
            seen = set()
            for x, y, w, h in tm.room_rects.values():
                block = {(tx, ty) for ty in range(y, y + h) for tx in range(x, x + w)}
                self.assertFalse(block & seen)
                seen |= block

    def test_floor_tiles_reachable_from_spawn(self):
        """Главное: проходимость на тайлах совпадает со связностью графа комнат."""
        walkable = (T.Tile.FLOOR, T.Tile.DOORWAY)
        for floor, tm in self.pairs:
            with self.subTest(seed=floor.seed):
                start = tm.room_center(self.cfg.spawn)
                seen = {start}
                q = deque([start])
                while q:
                    x, y = q.popleft()
                    for nx, ny in ((x+1, y), (x-1, y), (x, y+1), (x, y-1)):
                        if (nx, ny) not in seen and tm.at(nx, ny) in walkable:
                            seen.add((nx, ny))
                            q.append((nx, ny))
                for cell in floor.rooms():
                    self.assertIn(tm.room_center(cell), seen,
                                  f"комната {cell} недостижима по тайлам")

    def test_corridor_exists_exactly_for_doors(self):
        """Соседние комнаты без двери не должны соединяться коридором."""
        for floor, tm in self.pairs:
            for a in floor.rooms():
                for b in floor.rooms():
                    if a >= b or abs(a[0]-b[0]) + abs(a[1]-b[1]) != 1:
                        continue
                    linked = frozenset((a, b)) in floor.doors
                    ax, ay, aw, ah = tm.room_rects[a]
                    if a[0] == b[0]:
                        probe = (ax + aw, ay + ah // 2)
                    else:
                        probe = (ax + aw // 2, ay + ah)
                    walkable = tm.at(*probe) in (T.Tile.FLOOR, T.Tile.DOORWAY)
                    self.assertEqual(walkable, linked,
                                     f"seed {floor.seed}: {a}–{b} дверь={linked}, "
                                     f"проход={walkable}")

    def test_stairs_unreachable_without_boss_room(self):
        """То же правило, что и в графе, но проверенное на тайлах."""
        walkable = (T.Tile.FLOOR, T.Tile.DOORWAY)
        for floor, tm in self.pairs:
            bx, by, bw, bh = tm.room_rects[self.cfg.boss]
            boss_block = {(tx, ty) for ty in range(by, by + bh) for tx in range(bx, bx + bw)}
            start = tm.room_center(self.cfg.spawn)
            seen = {start}
            q = deque([start])
            while q:
                x, y = q.popleft()
                for nx, ny in ((x+1, y), (x-1, y), (x, y+1), (x, y-1)):
                    if (nx, ny) in seen or (nx, ny) in boss_block:
                        continue
                    if tm.at(nx, ny) in walkable:
                        seen.add((nx, ny))
                        q.append((nx, ny))
            with self.subTest(seed=floor.seed):
                self.assertNotIn(tm.room_center(floor.stairs), seen)

    def test_props_have_room_to_stand(self):
        """В каждой комнате остаётся место под предметы и врагов."""
        for floor, tm in self.pairs:
            for cell in floor.rooms():
                self.assertGreaterEqual(len(tm.interior(cell)), 40)

    def test_export_is_json_serialisable(self):
        import json

        floor, tm = self.pairs[0]
        data = T.to_dict(floor, tm)
        text = json.dumps(data, ensure_ascii=False)
        back = json.loads(text)
        self.assertEqual(len(back["rooms"]), len(floor.rooms()))
        self.assertEqual(len(back["tiles"]["rows"]), tm.height)
        self.assertTrue(all(len(r) == tm.width for r in back["tiles"]["rows"]))


class TestAtlas(unittest.TestCase):
    """Спрайты действительно вырезаются и не пустые."""

    def test_all_named_sprites_load(self):
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            self.skipTest("нет Pillow")
        from roomgen.sprites import ENEMIES, FLOOR_FAMILIES, PROPS, WALL_BRICK, Atlas

        atlas = Atlas()
        for key in PROPS:
            img = atlas.prop(key)
            self.assertTrue(img.width and img.height, key)
            self.assertIsNotNone(img.getbbox(), f"{key}: вырезка пустая")
        for key in ENEMIES:
            self.assertIsNotNone(atlas.enemy(key).getbbox(), key)
        self.assertIsNotNone(atlas.hero().getbbox())
        for family in FLOOR_FAMILIES:
            self.assertEqual(atlas.floor_tile(family, 0).size, (16, 16))
        for brick in WALL_BRICK:
            self.assertEqual(atlas.wall_tile(brick).size, (16, 16))

    def test_every_room_type_has_a_theme(self):
        for room_type in RoomType:
            if room_type is RoomType.EMPTY:
                continue
            self.assertIn(room_type, T.THEME)


if __name__ == "__main__":
    unittest.main(verbosity=2)
