"""CLI: `python -m roomgen <команда>`.

  show   [--seed N]                 — один этаж в терминале (ASCII)
  render [--seed N] [--out DIR]     — PNG: схема этажа, лист сидов, статистика
  pixels [--seed N] [--floor N]     — PNG: этаж реальными спрайтами проекта
  export [--seed N] [--out FILE]    — JSON с сеткой тайлов для сцены Godot
  check  [--count N]                — прогнать N сидов через проверки шага 8
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

from .ascii_render import render, render_summary
from .config import GenConfig, RoomType
from .generator import generate
from .validation import validate


def cmd_show(args) -> int:
    floor = generate(args.seed)
    print(render(floor))
    print()
    print(render_summary(floor))
    return 0


def cmd_render(args) -> int:
    from .viz import figure_floor, figure_sheet, figure_stats

    os.makedirs(args.out, exist_ok=True)
    floor = generate(args.seed)
    print(figure_floor(floor, os.path.join(args.out, "floor.png")))
    print(figure_sheet(range(args.seed + 1, args.seed + 9),
                       os.path.join(args.out, "sheet.png")))
    print(figure_stats(args.count, os.path.join(args.out, "stats.png")))
    return 0


def cmd_pixels(args) -> int:
    from .render_sprites import render_annotated, render_floor, render_room

    os.makedirs(args.out, exist_ok=True)
    floor = generate(args.seed)
    print(render_floor(floor, os.path.join(args.out, "pixels_floor.png"),
                       scale=args.scale, floor_number=args.floor))
    print(render_annotated(floor, os.path.join(args.out, "pixels_annotated.png"),
                           scale=args.scale, floor_number=args.floor))
    for cell in sorted(floor.rooms()):
        if floor.type_at(cell) is RoomType[args.room.upper()]:
            print(render_room(floor, cell, os.path.join(args.out, "pixels_room.png"),
                              floor_number=args.floor))
            break
    return 0


def cmd_export(args) -> int:
    import json

    from .tilemap import to_dict

    floor = generate(args.seed)
    data = to_dict(floor)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print(f"{args.out}: {len(data['rooms'])} комнат, "
          f"сетка {data['tiles']['width']}×{data['tiles']['height']} тайлов")
    return 0


def cmd_check(args) -> int:
    cfg = GenConfig()
    failures = 0
    totals, attempts = [], []
    presence: Counter = Counter()
    for seed in range(args.count):
        floor = generate(seed, cfg)
        errors = validate(floor)
        if errors:
            failures += 1
            print(f"seed {seed}: {errors}", file=sys.stderr)
        totals.append(len(floor.rooms()))
        attempts.append(floor.attempts)
        for room_type in floor.counts():
            presence[room_type] += 1
    from . import tilemap as tilemap_mod

    sample = min(args.count, 300)
    forced = [
        tilemap_mod.rooms_to_boss(f, tilemap_mod.build(f)) + 1
        for f in (generate(s, cfg) for s in range(sample))
    ]
    print(f"проверено этажей: {args.count}, с нарушениями: {failures}")
    print(f"комнат обязательно пройти до босса: "
          f"min {min(forced)}, среднее {sum(forced)/len(forced):.2f}, max {max(forced)} "
          f"(ГДД: 5–6, выборка {sample})")
    print(f"комнат на этаже: min {min(totals)}, среднее {sum(totals)/len(totals):.2f}, "
          f"max {max(totals)}")
    print(f"попыток генерации на этаж: среднее {sum(attempts)/len(attempts):.3f}, "
          f"max {max(attempts)}")
    for room_type in (RoomType.CHEST, RoomType.CAFETERIA, RoomType.TOILET,
                      RoomType.EVENT, RoomType.HARD):
        share = presence[room_type] / args.count * 100
        print(f"  {room_type.value:<10} встречается на {share:5.1f}% этажей")
    return 1 if failures else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="roomgen", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_show = sub.add_parser("show", help="этаж в терминале")
    p_show.add_argument("--seed", type=int, default=12)
    p_show.set_defaults(func=cmd_show)

    p_render = sub.add_parser("render", help="PNG-визуализация")
    p_render.add_argument("--seed", type=int, default=12)
    p_render.add_argument("--out", default="out")
    p_render.add_argument("--count", type=int, default=1500,
                          help="сколько этажей взять для графиков статистики")
    p_render.set_defaults(func=cmd_render)

    p_pixels = sub.add_parser("pixels", help="рендер реальными спрайтами")
    p_pixels.add_argument("--seed", type=int, default=12)
    p_pixels.add_argument("--out", default="out")
    p_pixels.add_argument("--scale", type=int, default=2)
    p_pixels.add_argument("--floor", type=int, default=1,
                          help="номер этажа: от него зависит число врагов")
    p_pixels.add_argument("--room", default="cafeteria",
                          help="тип комнаты для крупного плана")
    p_pixels.set_defaults(func=cmd_pixels)

    p_export = sub.add_parser("export", help="JSON для сцены Godot")
    p_export.add_argument("--seed", type=int, default=12)
    p_export.add_argument("--out", default="out/floor.json")
    p_export.set_defaults(func=cmd_export)

    p_check = sub.add_parser("check", help="прогон проверок шага 8")
    p_check.add_argument("--count", type=int, default=2000)
    p_check.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
