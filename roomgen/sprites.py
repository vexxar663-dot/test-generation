"""Атлас реальных спрайтов проекта (`spites/` — как в Godot-проекте, `res://spites/`).

Здесь только координаты вырезок и ленивая загрузка. Логика генерации об этом
модуле ничего не знает: `tilemap.py` отдаёт номера тайлов, а рендер уже решает,
каким спрайтом их нарисовать.

Координаты получены разбором листов (связные непрозрачные области), а не на глаз;
`Atlas.get()` дополнительно обрезает прозрачные поля вырезки.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

Rect = Tuple[int, int, int, int]  # x, y, w, h

#: Корень с исходными листами. В Godot-проекте это res://spites/.
SPRITE_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "spites")

SHEET_TILES = "floors/tiles.png"
SHEET_WALLS = "walls/floor_walls.png"
SHEET_FURNITURE = "objects/furniture (2).png"
SHEET_UI = "ui/coins-chests-etc-2-0.png"
SHEET_HERO = "heros/main_hero/nameless.png"
SHEET_ENEMIES = "heros/enemies/enemies.png"

#: floors/tiles.png — ровная сетка: тайл 16×16, шаг 32, начало (16,16).
TILE_SIZE = 16
_TILE_ORIGIN = 16
_TILE_PITCH = 32


def tile(col: int, row: int) -> Rect:
    """Вырезка тайла из floors/tiles.png по позиции в его сетке."""
    return (_TILE_ORIGIN + _TILE_PITCH * col, _TILE_ORIGIN + _TILE_PITCH * row,
            TILE_SIZE, TILE_SIZE)


# --- Семейства полов и стен ------------------------------------------------
# Ряд 0 — кирпичные стены (5 цветов), ряд 1 — паркет, ряд 2 — школьная плитка,
# ряды 3–5 белый пол, 6–8 синий, 9–11 зелёный (по 3 ряда на семейство:
# верх/середина/низ, для заливки берём середину).

WALL_BRICK: Dict[str, Rect] = {
    "brown": tile(0, 0), "light": tile(1, 0), "orange": tile(2, 0),
    "white": tile(3, 0), "red": tile(4, 0),
}

FLOOR_FAMILIES: Dict[str, List[Rect]] = {
    "parquet": [tile(c, 1) for c in range(4)],   # столовая
    "school":  [tile(c, 2) for c in range(4)],   # обычные комнаты и коридоры
    "white":   [tile(c, 4) for c in range(4)],   # толчок
    "blue":    [tile(c, 7) for c in range(4)],   # сундук, ивент
    "green":   [tile(c, 10) for c in range(4)],  # спавн
    "red":     [tile(4, 1)],                     # босс
}

# --- Предметы --------------------------------------------------------------
PROPS: Dict[str, Tuple[str, Rect]] = {
    "toilet":      (SHEET_FURNITURE, (752, 310, 20, 42)),
    "sink":        (SHEET_FURNITURE, (656, 298, 62, 54)),
    "fridge":      (SHEET_FURNITURE, (512, 296, 28, 56)),
    "stove":       (SHEET_FURNITURE, (544, 313, 30, 39)),
    "counter":     (SHEET_FURNITURE, (576, 320, 64, 32)),
    "board":       (SHEET_FURNITURE, (0, 389, 66, 43)),
    "desk":        (SHEET_FURNITURE, (144, 313, 48, 39)),
    "bookshelf":   (SHEET_FURNITURE, (144, 206, 50, 66)),
    "locker":      (SHEET_FURNITURE, (80, 384, 20, 48)),
    "door":        (SHEET_WALLS, (223, 4, 35, 60)),
    "chest_wood":  (SHEET_UI, (16, 540, 16, 20)),
    "chest_gold":  (SHEET_UI, (256, 540, 16, 20)),
    "coin":        (SHEET_UI, (64, 146, 16, 16)),
    "star":        (SHEET_UI, (64, 194, 16, 16)),
    "heart":       (SHEET_UI, (320, 194, 16, 16)),
}

# --- Персонажи -------------------------------------------------------------
HERO: Tuple[str, Rect] = (SHEET_HERO, (23, 28, 20, 36))

ENEMIES: Dict[str, Tuple[str, Rect]] = {
    "shadow_a":   (SHEET_ENEMIES, (70, 96, 18, 48)),
    "shadow_b":   (SHEET_ENEMIES, (134, 96, 18, 48)),
    "shadow_thin": (SHEET_ENEMIES, (167, 96, 16, 48)),
    "hat":        (SHEET_ENEMIES, (99, 159, 24, 49)),
    "horned":     (SHEET_ENEMIES, (176, 167, 32, 41)),
    "elite":      (SHEET_ENEMIES, (272, 170, 36, 38)),
    "boss":       (SHEET_ENEMIES, (336, 96, 30, 48)),
}

#: Рядовые враги (ГДД 4.4: «Переписанные» — силуэты без лиц).
MOB_KEYS = ("shadow_a", "shadow_b", "shadow_thin", "hat", "horned")


class Atlas:
    """Ленивая загрузка листов и вырезок. Требует Pillow."""

    def __init__(self, root: str = SPRITE_ROOT):
        self.root = root
        self._sheets: Dict[str, object] = {}
        self._cache: Dict[Tuple[str, Rect, bool], object] = {}

    def sheet(self, name: str):
        if name not in self._sheets:
            from PIL import Image

            path = os.path.join(self.root, name)
            if not os.path.exists(path):
                raise FileNotFoundError(
                    f"нет спрайт-листа {path}. Папка spites/ должна лежать "
                    f"рядом с roomgen/ (в Godot-проекте это res://spites/)."
                )
            self._sheets[name] = Image.open(path).convert("RGBA")
        return self._sheets[name]

    def get(self, name: str, rect: Rect, trim: bool = True):
        """Вырезка из листа; trim убирает прозрачные поля."""
        key = (name, rect, trim)
        if key not in self._cache:
            x, y, w, h = rect
            img = self.sheet(name).crop((x, y, x + w, y + h))
            if trim:
                box = img.getbbox()
                if box:
                    img = img.crop(box)
            self._cache[key] = img
        return self._cache[key]

    def prop(self, key: str):
        sheet, rect = PROPS[key]
        return self.get(sheet, rect)

    def enemy(self, key: str):
        sheet, rect = ENEMIES[key]
        return self.get(sheet, rect)

    def hero(self):
        sheet, rect = HERO
        return self.get(sheet, rect)

    def floor_tile(self, family: str, variant: int):
        variants = FLOOR_FAMILIES[family]
        return self.get(SHEET_TILES, variants[variant % len(variants)], trim=False)

    def wall_tile(self, color: str):
        return self.get(SHEET_TILES, WALL_BRICK[color], trim=False)
