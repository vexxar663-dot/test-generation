"""Рендер сгенерированного этажа реальными спрайтами проекта.

Пиксель-арт рисуется в масштабе 1:1 (тайл 16×16), и только готовая картинка
увеличивается методом ближайшего соседа — так пиксели остаются пикселями.

Выходы:
  render_floor   — весь этаж целиком (карта уровня, как он выглядит в игре);
  render_room    — одна комната крупно;
  render_legend  — тот же этаж плюс подписи и легенда со спрайтами.
"""

from __future__ import annotations

import os
import random
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

from . import tilemap as T
from .config import METERS_PER_TILE, RU_NAME, RoomType
from .generator import Floor
from .sprites import MOB_KEYS, TILE_SIZE, Atlas

BACKDROP = (18, 18, 17, 255)
INK = (232, 230, 221)
INK_MUTED = (138, 136, 126)


def _font(size: int):
    """DejaVu Sans из поставки matplotlib — в нём есть кириллица."""
    try:
        import matplotlib

        path = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans.ttf")
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Наполнение комнаты предметами
# ---------------------------------------------------------------------------

#: Что стоит в комнате: (спрайт, режим раскладки, сколько).
#:   "wall"     — вдоль верхней стены, число фиксировано (доска, плита);
#:   "wall_row" — вдоль верхней стены, число растёт с площадью (шкафчики, кабинки);
#:   "rows"     — рядами по всей комнате, число растёт с площадью (парты, столы);
#:   "free"     — врассыпную, число фиксировано (сундук, монеты, стойки с перками).
ROOM_PROPS: Dict[RoomType, Sequence[Tuple[str, str, int]]] = {
    RoomType.SPAWN:     (("locker", "wall_row", 6),),
    RoomType.NORMAL:    (("board", "wall", 1), ("desk", "rows", 9)),
    RoomType.HARD:      (("board", "wall", 1), ("desk", "rows", 6)),
    RoomType.CAFETERIA: (("fridge", "wall", 1), ("stove", "wall", 1),
                         ("counter", "wall_row", 2), ("desk", "rows", 6),
                         ("coin", "free", 4)),
    RoomType.TOILET:    (("toilet", "wall_row", 3), ("sink", "wall_row", 1)),
    RoomType.CHEST:     (("chest_wood", "free", 1), ("coin", "free", 3)),
    RoomType.EVENT:     (("board", "wall", 1), ("bookshelf", "wall_row", 2),
                         ("desk", "rows", 6)),
    RoomType.STAIRS:    (("door", "wall", 1), ("star", "free", 3)),
    RoomType.BOSS:      (),
}

#: Площадь пола обычного класса в тайлах — опора для числа врагов. Бой в
#: комнате по ГДД длится 5–15 секунд, поэтому враги считаются от комнаты,
#: а не от квадратных метров.
REFERENCE_INTERIOR = 1250

#: А мебель заполняет площадь, поэтому её плотность привязана к метрам:
#: столько тайлов пола приходилось на один предмет в комнате прежнего размера.
PROP_REFERENCE_INTERIOR = 300


def _area_scale(interior: int, power: float = 0.5,
                reference: int = REFERENCE_INTERIOR) -> float:
    """Во сколько раз комната крупнее опорной (с затуханием по умолчанию)."""
    return max(interior / reference, 0.05) ** power


def _enemy_count(room_type: RoomType, floor_number: int, interior: int) -> int:
    """ГДД 4.4: с каждым этажом растёт число врагов.

    По площади масштабируем с корнем: бой в обычной комнате по ГДД длится
    5–15 секунд, и линейный рост от площади сделал бы это время недостижимым.
    """
    if room_type is RoomType.NORMAL:
        base = 4 + floor_number
    elif room_type is RoomType.HARD:
        base = 6 + floor_number          # «врагов на 20–30% больше» + элита
    elif room_type is RoomType.BOSS:
        base = 3
    else:
        return 0
    return max(1, round(base * _area_scale(interior)))


def _paste(canvas: Image.Image, sprite: Image.Image, tile_xy: Tuple[int, int],
           tile_px: int = TILE_SIZE, origin: Tuple[int, int] = (0, 0)) -> None:
    """Поставить спрайт на тайл: по центру по горизонтали, «ногами» на нижний край."""
    tx, ty = tile_xy[0] - origin[0], tile_xy[1] - origin[1]
    x = tx * tile_px + (tile_px - sprite.width) // 2
    y = ty * tile_px + tile_px - sprite.height
    if x + sprite.width <= 0 or y + sprite.height <= 0:
        return
    canvas.alpha_composite(sprite, (max(x, 0), max(y, 0)))


def _cells(sprite: Image.Image) -> Tuple[int, int]:
    """Сколько тайлов занимает спрайт по ширине и высоте."""
    return (-(-sprite.width // TILE_SIZE), -(-sprite.height // TILE_SIZE))


class _Placer:
    """Раскладка предметов по комнате без наложений и без вылезания за стены.

    Спрайт «стоит» на тайле: центрируется по горизонтали и растёт вверх, поэтому
    занимаемая площадь считается от точки опоры, а высокие шкафы сами отходят
    от верхней стены на нужное число тайлов.
    """

    def __init__(self, tm: T.TileMap, cell, rng: random.Random):
        self.free = set(tm.interior(cell))
        self.top = tm.room_rects[cell][1] + 1
        self.rng = rng

    def _footprint(self, tx: int, ty: int, sprite: Image.Image, margin: int = 0):
        cols, rows = _cells(sprite)
        left = tx - (cols - 1) // 2
        return [(cx, cy)
                for cx in range(left - margin, left + cols + margin)
                for cy in range(ty - rows + 1 - margin, ty + 1 + margin)]

    def reserve(self, sprite: Image.Image, spot, margin: int = 0) -> None:
        """Занять место под спрайт, поставленный в заранее известную точку."""
        for c in self._footprint(spot[0], spot[1], sprite, margin):
            self.free.discard(c)

    def place_at(self, sprite: Image.Image, spot, margin: int = 0) -> bool:
        """Поставить в конкретный тайл, если он свободен."""
        if any(c not in self.free for c in self._footprint(spot[0], spot[1], sprite)):
            return False
        self.reserve(sprite, spot, margin)
        return True

    def lattice(self, sprite: Image.Image, step_x: int, step_y: int):
        """Точки опоры ровными рядами — парты в классе, а не россыпью."""
        if not self.free:
            return []
        xs = sorted({x for x, _ in self.free})
        ys = sorted({y for _, y in self.free})
        cols = xs[1::step_x]
        rows = ys[2::step_y]
        return [(x, y) for y in rows for x in cols]

    def place(self, sprite: Image.Image, at_wall: bool = False, margin: int = 0):
        """Занять место под спрайт. Возвращает тайл опоры или None.

        margin оставляет зазор вокруг — фигуры не слипаются в один силуэт.
        """
        fits = [s for s in self.free
                if all(c in self.free for c in self._footprint(s[0], s[1], sprite))]
        if not fits:
            return None
        if at_wall:  # прижать к верхней стене, насколько позволяет высота
            top_row = min(ty for _, ty in fits)
            fits = [s for s in fits if s[1] == top_row]
        pick = self.rng.choice(sorted(fits))
        self.reserve(sprite, pick, margin)
        return pick


# ---------------------------------------------------------------------------
# Основной рендер
# ---------------------------------------------------------------------------

def draw_map(floor: Floor, atlas: Optional[Atlas] = None, floor_number: int = 1,
             tile_px: int = TILE_SIZE,
             region: Optional[Tuple[int, int, int, int]] = None,
             ) -> Tuple[Image.Image, T.TileMap]:
    """Нарисовать этаж. tile_px < 16 даёт уменьшенный обзор целого этажа.

    После увеличения комнат карта в масштабе 1:1 — это около 110 мегапикселей,
    поэтому обзорную картинку рисуем сразу мелким тайлом, а не уменьшаем готовую.
    """
    atlas = atlas or Atlas()
    tm = T.build(floor)
    x0, y0, x1, y1 = region or (0, 0, tm.width, tm.height)
    canvas = Image.new("RGBA", ((x1 - x0) * tile_px, (y1 - y0) * tile_px), BACKDROP)
    rng = random.Random(floor.seed * 7919 + floor_number)
    ratio = tile_px / TILE_SIZE
    cache: Dict[int, Image.Image] = {}

    def scaled(sprite: Image.Image) -> Image.Image:
        if tile_px == TILE_SIZE:
            return sprite
        key = id(sprite)
        if key not in cache:
            cache[key] = sprite.resize(
                (max(1, round(sprite.width * ratio)), max(1, round(sprite.height * ratio))),
                Image.NEAREST,
            )
        return cache[key]

    # 1. Пол и стены.
    for ty in range(y0, y1):
        for tx in range(x0, x1):
            kind = tm.tiles[ty][tx]
            if kind is T.Tile.EMPTY:
                continue
            owner = tm.owner.get((tx, ty))
            family, brick = (T.THEME[floor.type_at(owner)] if owner else T.CORRIDOR_THEME)
            if kind is T.Tile.WALL:
                sprite = atlas.wall_tile(brick)
            else:
                # Коридор и проёмы всегда школьной плиткой — проход читается как проход.
                if kind in (T.Tile.HALL, T.Tile.DOORWAY):
                    family = T.CORRIDOR_THEME[0]
                variant = (tx * 31 + ty * 17 + floor.seed) % 4
                sprite = atlas.floor_tile(family, variant)
            canvas.alpha_composite(scaled(sprite),
                                   ((tx - x0) * tile_px, (ty - y0) * tile_px))

    # 2. Предметы, герой и враги.
    for cell in floor.rooms():
        room_type = floor.type_at(cell)
        rx, ry, rw, rh = tm.room_rects[cell]
        if rx >= x1 or ry >= y1 or rx + rw <= x0 or ry + rh <= y0:
            continue          # комната вне запрошенного куска карты
        placer = _Placer(tm, cell, rng)

        interior = len(tm.interior(cell))

        def put(sprite, at_wall=False, spot=None, margin=0):
            if spot is None:
                spot = placer.place(sprite, at_wall, margin)
            else:
                placer.reserve(sprite, spot, margin)  # герой/босс — место под них
            if spot:
                _paste(canvas, scaled(sprite), spot, tile_px, (x0, y0))
            return spot

        for key, mode, count in ROOM_PROPS.get(room_type, ()):
            sprite = atlas.prop(key)
            if mode == "rows":
                # Мебель заполняет площадь, поэтому её число растёт линейно.
                want = max(1, round(count * _area_scale(
                    interior, power=1.0, reference=PROP_REFERENCE_INTERIOR)))
                spots = placer.lattice(sprite, step_x=4, step_y=3)
                if len(spots) > want:   # разредить, но оставить рядами
                    spots = spots[::max(1, len(spots) // want)]
                placed = 0
                for spot in spots:
                    if placed >= want:
                        break
                    if placer.place_at(sprite, spot):
                        _paste(canvas, scaled(sprite), spot, tile_px, (x0, y0))
                        placed += 1
                continue
            if mode == "wall_row":
                count = max(1, round(count * _area_scale(
                    interior, reference=PROP_REFERENCE_INTERIOR)))
            for _ in range(count):
                put(sprite, at_wall=mode.startswith("wall"))

        # Второй сундук в комнате — золотой, чтобы читалась разная награда.
        if room_type is RoomType.CHEST and rng.random() < 0.5:
            put(atlas.prop("chest_gold"))

        if room_type is RoomType.SPAWN:
            put(atlas.hero(), spot=tm.room_center(cell), margin=1)

        n = _enemy_count(room_type, floor_number, interior)
        if room_type is RoomType.BOSS:
            put(atlas.enemy("boss"), spot=tm.room_center(cell), margin=1)
        if room_type is RoomType.HARD:
            if put(atlas.enemy("elite"), margin=1):
                n -= 1
        for _ in range(max(n, 0)):
            if not put(atlas.enemy(rng.choice(MOB_KEYS)), margin=1):
                break

    return canvas, tm


def render_floor(floor: Floor, path: str, scale: int = 1, floor_number: int = 1,
                 atlas: Optional[Atlas] = None, tile_px: int = 8) -> str:
    """Чистая карта уровня без подписей (по умолчанию — обзорная, тайл 4 px)."""
    canvas, _ = draw_map(floor, atlas, floor_number, tile_px)
    if scale != 1:
        canvas = canvas.resize((canvas.width * scale, canvas.height * scale), Image.NEAREST)
    canvas.convert("RGB").save(path)
    return path


def render_room(floor: Floor, cell, path: str, scale: int = 1,
                floor_number: int = 1, atlas: Optional[Atlas] = None,
                tile_px: int = TILE_SIZE) -> str:
    """Одна комната крупно — видно, как читается тайлсет вблизи."""
    tm = T.build(floor)
    x, y, w, h = tm.room_rects[cell]
    pad = 10
    region = (max(x - pad, 0), max(y - pad, 0),
              min(x + w + pad, tm.width), min(y + h + pad, tm.height))
    # Рисуем только нужный кусок: карта целиком в масштабе 1:1 — это больше
    # ста мегапикселей, и держать её в памяти ради одной комнаты ни к чему.
    crop, _ = draw_map(floor, atlas, floor_number, tile_px, region)
    if scale != 1:
        crop = crop.resize((crop.width * scale, crop.height * scale), Image.NEAREST)
    crop.convert("RGB").save(path)
    return path


#: Что показать в легенде: тип комнаты → спрайт-образец.
_LEGEND: Sequence[Tuple[RoomType, str, str]] = (
    (RoomType.SPAWN, "hero", ""),
    (RoomType.NORMAL, "enemy:shadow_a", ""),
    (RoomType.HARD, "enemy:elite", "элита, рычаг сложности"),
    (RoomType.CHEST, "prop:chest_wood", ""),
    (RoomType.CAFETERIA, "prop:fridge", ""),
    (RoomType.TOILET, "prop:toilet", ""),
    (RoomType.EVENT, "prop:board", "головоломка"),
    (RoomType.BOSS, "enemy:boss", ""),
    (RoomType.STAIRS, "prop:door", "только после босса"),
)


def _legend_sprite(atlas: Atlas, spec: str) -> Image.Image:
    if spec == "hero":
        return atlas.hero()
    kind, key = spec.split(":")
    return atlas.enemy(key) if kind == "enemy" else atlas.prop(key)


def render_annotated(floor: Floor, path: str, scale: int = 1, floor_number: int = 1,
                     atlas: Optional[Atlas] = None, tile_px: int = 8) -> str:
    """Карта + подписи комнат + легенда со спрайтами (обзорная, тайл 8 px)."""
    atlas = atlas or Atlas()
    canvas, tm = draw_map(floor, atlas, floor_number, tile_px)
    big = canvas if scale == 1 else canvas.resize(
        (canvas.width * scale, canvas.height * scale), Image.NEAREST)

    head, legend_h, pad = 96, 150, 24
    out = Image.new("RGBA", (big.width + pad * 2, big.height + head + legend_h + pad),
                    BACKDROP)
    out.alpha_composite(big, (pad, head))
    d = ImageDraw.Draw(out)

    f_title, f_text, f_small = _font(26), _font(15), _font(13)
    counts = floor.counts()
    d.text((pad, 14), f"Equation Dodge — этаж {floor_number}, seed {floor.seed}",
           font=f_title, fill=INK)
    forced = T.rooms_to_boss(floor, tm)
    loops = len(floor.corridors) - len(floor.rooms()) + 1
    d.text((pad, 44),
           f"{len(floor.rooms())} комнат · до босса обязательно пройти {forced} "
           f"(ГДД: 5–6) · петель {loops} · {tm.width}×{tm.height} тайлов "
           f"≈ {tm.width*METERS_PER_TILE:.0f}×{tm.height*METERS_PER_TILE:.0f} м · "
           f"обзор в {TILE_SIZE//tile_px}× уменьшении",
           font=f_small, fill=INK_MUTED)

    # Подписи комнат — поверх верхней стены блока.
    for cell in floor.rooms():
        room_type = floor.type_at(cell)
        x, y, w, _h = tm.room_rects[cell]
        label = RU_NAME[room_type]
        cx = pad + (x + w / 2) * tile_px * scale
        cy = head + y * tile_px * scale - 15
        box = d.textbbox((cx, cy), label, font=f_small, anchor="mm")
        d.rectangle([box[0] - 5, box[1] - 3, box[2] + 5, box[3] + 3], fill=BACKDROP)
        d.text((cx, cy), label, font=f_small, fill=INK_MUTED, anchor="mm")

    # Легенда.
    ly = head + big.height + 22
    d.line([(pad, ly - 10), (out.width - pad, ly - 10)], fill=(46, 46, 43), width=2)
    col_w = (out.width - pad * 2) // 5
    for i, (room_type, spec, note) in enumerate(_LEGEND):
        cx = pad + (i % 5) * col_w
        cy = ly + (i // 5) * 64
        sprite = _legend_sprite(atlas, spec)
        k = min(3, max(1, 40 // max(sprite.height, 1)))
        thumb = sprite.resize((sprite.width * k, sprite.height * k), Image.NEAREST)
        out.alpha_composite(thumb, (cx, cy + max(0, 46 - thumb.height)))
        tx = cx + max(56, thumb.width + 12)
        n = counts.get(room_type, 0)
        d.text((tx, cy + 8), f"{RU_NAME[room_type]} ×{n}", font=f_text, fill=INK)
        if note:
            d.text((tx, cy + 28), note, font=f_small, fill=INK_MUTED)

    out.convert("RGB").save(path)
    return path
