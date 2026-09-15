"""Схема этажа на matplotlib — та же планировка, что и в пиксель-рендере.

Три фигуры:
  figure_floor  — один этаж крупно: схема, легенда, счётчики, тайминг;
  figure_sheet  — лист из нескольких сидов (проверка разнообразия «на глаз»);
  figure_stats  — распределения по N этажам против требований ГДД.
"""

from __future__ import annotations

from collections import Counter
from typing import List, Optional, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch, Rectangle

from . import palette as P
from .config import GLYPH, METERS_PER_TILE, RU_NAME, RoomType
from .generator import Floor, generate

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "figure.facecolor": P.SURFACE,
    "axes.facecolor": P.SURFACE,
    "savefig.facecolor": P.SURFACE,
    "text.color": P.TEXT_SECONDARY,
    "axes.labelcolor": P.TEXT_SECONDARY,
    "xtick.color": P.TEXT_MUTED,
    "ytick.color": P.TEXT_MUTED,
    "axes.edgecolor": P.GRID_LINE,
})


def draw_floor(ax, floor: Floor, labels: bool = True, glyph_size: float = 8.0) -> None:
    """Нарисовать планировку: комнаты прямоугольниками, перемычки полосами."""
    ax.set_xlim(-2, floor.width + 2)
    ax.set_ylim(-floor.height - 2, 2)
    ax.set_aspect("equal")
    ax.axis("off")

    route = set(floor.critical_path())

    # 1. Перемычки — под комнатами, чтобы не резали их рамки.
    for door, corridor in floor.corridors.items():
        on_route = len(door & route) == 2
        ax.add_patch(Rectangle(
            (corridor.x, -(corridor.y + corridor.h)), corridor.w, corridor.h,
            facecolor=P.PATH_COLOR if on_route else P.DOOR_COLOR,
            edgecolor="none", zorder=1,
        ))

    # 2. Комнаты.
    for rid in floor.rooms():
        room = floor.room(rid)
        style = P.STYLES[room.type]
        ax.add_patch(FancyBboxPatch(
            (room.x, -room.y2), room.w, room.h,
            boxstyle="round,pad=0,rounding_size=1.2",
            facecolor=style.fill, edgecolor=style.edge, linewidth=style.lw,
            zorder=2,
        ))
        cx, cy = room.x + room.w / 2, -(room.y + room.h / 2)
        if labels and room.w >= 12:
            ax.text(cx, cy + 1.2, GLYPH[room.type], ha="center", va="center",
                    color=style.ink, fontsize=glyph_size * 1.3,
                    fontweight="bold", zorder=3)
            ax.text(cx, cy - 2.2, RU_NAME[room.type].upper(), ha="center", va="center",
                    color=style.ink, fontsize=glyph_size * 0.72, zorder=3)
        else:
            ax.text(cx, cy, GLYPH[room.type], ha="center", va="center",
                    color=style.ink, fontsize=glyph_size, fontweight="bold", zorder=3)


def _legend_handles() -> List[Line2D]:
    handles = []
    for room_type in P.LEGEND_ORDER:
        style = P.STYLES[room_type]
        handles.append(Line2D(
            [], [], marker="s", linestyle="none", markersize=9,
            markerfacecolor=style.fill, markeredgecolor=style.edge, markeredgewidth=1.4,
            label=f"{GLYPH[room_type]}  {RU_NAME[room_type]}",
        ))
    handles.append(Line2D([], [], color=P.PATH_COLOR, lw=4,
                          label="обязательный маршрут"))
    handles.append(Line2D([], [], color=P.DOOR_COLOR, lw=4, label="перемычка"))
    return handles


def figure_floor(floor: Floor, path: str) -> str:
    """Один этаж крупно: схема + легенда + сводка."""
    fig = plt.figure(figsize=(14.5, 8.0))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.65, 1.0], wspace=0.02,
                          left=0.025, right=0.985, top=0.87, bottom=0.03)
    ax_map = fig.add_subplot(gs[0, 0])
    draw_floor(ax_map, floor)

    route = floor.critical_path()
    loops = len(floor.corridors) - len(floor.rooms()) + 1
    fig.text(0.03, 0.945, "Equation Dodge — генерация этажа",
             color=P.TEXT_PRIMARY, fontsize=18, fontweight="bold")
    fig.text(0.03, 0.905,
             f"seed {floor.seed} · {len(floor.rooms())} комнат · "
             f"{len(floor.corridors)} перемычек · петель {loops} · "
             f"{floor.width}×{floor.height} тайлов "
             f"≈ {floor.width*METERS_PER_TILE:.0f}×{floor.height*METERS_PER_TILE:.0f} м",
             color=P.TEXT_MUTED, fontsize=11)

    ax_side = fig.add_subplot(gs[0, 1])
    ax_side.axis("off")
    ax_side.legend(handles=_legend_handles(), loc="upper left", frameon=False,
                   labelspacing=0.78, handletextpad=0.9, fontsize=10.5,
                   labelcolor=P.TEXT_SECONDARY, bbox_to_anchor=(-0.02, 1.02))

    counts = floor.counts()
    lines = ["СОСТАВ ЭТАЖА"]
    for room_type in P.LEGEND_ORDER:
        n = counts.get(room_type, 0)
        lo, hi = floor.config.caps.get(room_type, (0, 0))
        flag = "" if lo <= n <= hi else "  ← вне лимита"
        short = "Лестница" if room_type is RoomType.STAIRS else RU_NAME[room_type]
        lines.append(f"{short:<13} {n}  (ГДД {lo}–{hi}){flag}")
    lo_all, hi_all = floor.time_estimate()
    lo_rt, hi_rt = floor.time_estimate(route)
    lines += [
        "",
        "ОБЯЗАТЕЛЬНЫЙ МАРШРУТ",
        f"{len(route)} комнат  (ГДД 3.1: 5–6)",
        "",
        "ТАЙМИНГ (ГДД: 5–7 мин на этаж)",
        f"только до босса   {lo_rt/60:.1f}–{hi_rt/60:.1f} мин",
        f"зачистка на 100%  {lo_all/60:.1f}–{hi_all/60:.1f} мин",
    ]
    ax_side.text(0.50, 1.02, "\n".join(lines), transform=ax_side.transAxes,
                 va="top", ha="left", fontsize=10, color=P.TEXT_SECONDARY,
                 family="DejaVu Sans Mono", linespacing=1.7)
    ax_side.text(
        -0.02, 0.34,
        "ЦВЕТ = КЛАСС, ГЛИФ = ТИП\n"
        "жёлтый — награда (сундук, ивент)\n"
        "аква — сервис (столовая, толчок)\n"
        "фиолетовый — риск (ставка)\n"
        "серый/белый — каркас этажа\n\n"
        "Размер комнаты задаёт её тип:\n"
        "боссфайт — зал, столовая широкая,\n"
        "толчок узкий, сундук маленький.\n"
        "Лестница висит только на боссе.",
        transform=ax_side.transAxes, va="top", ha="left",
        fontsize=9.5, color=P.TEXT_MUTED, linespacing=1.6,
    )
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def figure_sheet(seeds: Sequence[int], path: str, cols: int = 4, cfg=None) -> str:
    """Лист из нескольких этажей — быстрый контроль разнообразия."""
    floors = [generate(s, cfg) for s in seeds]
    rows = (len(floors) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(3.6 * cols, 3.7 * rows))
    axes = axes.ravel() if hasattr(axes, "ravel") else [axes]
    for ax, floor in zip(axes, floors):
        draw_floor(ax, floor, labels=False, glyph_size=7.0)
        loops = len(floor.corridors) - len(floor.rooms()) + 1
        ax.set_title(f"seed {floor.seed} · {len(floor.rooms())} комнат · "
                     f"маршрут {len(floor.critical_path())} · петель {loops}",
                     color=P.TEXT_SECONDARY, fontsize=9, pad=6)
    for ax in axes[len(floors):]:
        ax.axis("off")
    fig.suptitle("Разнообразие планировок по сидам", color=P.TEXT_PRIMARY,
                 fontsize=15, fontweight="bold", y=0.997)
    fig.tight_layout(rect=(0, 0, 1, 0.96), h_pad=2.6)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _band(ax, lo, hi, label):
    ax.axvspan(lo, hi, color=P.CHART_BAND, zorder=0)
    ax.text(lo, ax.get_ylim()[1] * 0.99, f" {label}", ha="left", va="top",
            fontsize=9, color=P.TEXT_MUTED)


def _style_axes(ax, title, xlabel):
    ax.set_title(title, color=P.TEXT_PRIMARY, fontsize=12, fontweight="bold",
                 loc="left", pad=10)
    ax.set_xlabel(xlabel, fontsize=10)
    ax.grid(axis="y", color=P.GRID_LINE, lw=0.8, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(P.GRID_LINE)
    ax.tick_params(labelsize=9)


def figure_stats(n: int, path: str, cfg=None) -> str:
    """Распределения по n этажам с наложенными требованиями ГДД."""
    totals, route_len, loops, times, t_lo, t_hi, attempts = [], [], [], [], [], [], []
    type_counts: Counter = Counter()
    presence: Counter = Counter()
    for seed in range(n):
        floor = generate(seed, cfg)
        totals.append(len(floor.rooms()))
        route_len.append(len(floor.critical_path()))
        loops.append(len(floor.corridors) - len(floor.rooms()) + 1)
        attempts.append(floor.attempts)
        lo, hi = floor.time_estimate()
        t_lo.append(lo / 60)
        t_hi.append(hi / 60)
        times.append((lo + hi) / 2 / 60)
        for room_type, count in floor.counts().items():
            type_counts[room_type] += count
            presence[room_type] += 1

    fig, axes = plt.subplots(2, 2, figsize=(13, 8.2))
    fig.suptitle(f"Контроль генератора на {n} сидах", color=P.TEXT_PRIMARY,
                 fontsize=16, fontweight="bold", x=0.045, ha="left", y=0.975)

    # 1. Комнат на этаже.
    ax = axes[0, 0]
    vals = sorted(Counter(totals).items())
    ax.bar([v for v, _ in vals], [c / n * 100 for _, c in vals],
           color=P.CHART_HUE, width=0.72, zorder=3)
    ax.set_ylabel("% этажей", fontsize=10)
    _style_axes(ax, "Комнат на этаже", "ГДД 3.1: 16–22, в среднем 18–20")
    top = max(c / n * 100 for _, c in vals)
    ax.set_ylim(0, top * 1.22)
    _band(ax, 17.5, 20.5, "среднее по ГДД: 18–20")
    mean_total = sum(totals) / n
    ax.vlines(mean_total, 0, top * 1.06, color=P.TEXT_SECONDARY, lw=1.6, ls="--", zorder=4)
    ax.text(mean_total, top * 0.72, f" факт {mean_total:.1f}",
            color=P.TEXT_SECONDARY, fontsize=9.5)

    # 2. Обязательный маршрут и петли.
    ax = axes[0, 1]
    vals = sorted(Counter(route_len).items())
    ax.bar([v for v, _ in vals], [c / n * 100 for _, c in vals],
           color=P.CHART_HUE, width=0.6, zorder=3)
    ax.set_ylabel("% этажей", fontsize=10)
    ax.set_xlim(2.5, 8.5)
    _style_axes(ax, "Комнат обязательно пройти до босса",
                f"петель (альтернативных маршрутов) в среднем {sum(loops)/n:.1f}")
    ax.set_ylim(0, max(c / n * 100 for _, c in vals) * 1.25)
    _band(ax, 4.5, 6.5, "ГДД 3.1: 5–6 комнат")

    # 3. Состав этажа.
    ax = axes[1, 0]
    order = list(P.LEGEND_ORDER)
    means = [type_counts[t] / n for t in order]
    ax.barh(list(range(len(order))), means,
            color=[P.STYLES[t].edge for t in order], height=0.66, zorder=3)
    ax.set_yticks(list(range(len(order))))
    ax.set_yticklabels([RU_NAME[t] for t in order], fontsize=9.5)
    ax.invert_yaxis()
    for i, (room_type, mean) in enumerate(zip(order, means)):
        ax.text(mean + 0.12, i, f"{mean:.2f}   (есть на {presence[room_type]/n*100:.0f}%)",
                va="center", fontsize=9, color=P.TEXT_SECONDARY)
    ax.set_xlim(0, max(means) * 1.75)
    _style_axes(ax, "Среднее число комнат каждого типа", "комнат на этаж")
    ax.grid(axis="y", visible=False)

    # 4. Время этажа.
    ax = axes[1, 1]
    ax.hist(times, bins=26, color=P.CHART_HUE, zorder=3)
    ax.set_ylabel("этажей", fontsize=10)
    _style_axes(ax, "Оценка времени зачистки на 100%",
                "ГДД: 5–7 мин на этаж (расчёт по таблице таймингов ГДД)")
    lo_m, hi_m = sum(t_lo) / n, sum(t_hi) / n
    ax.set_xlim(min(t_lo) - 0.3, max(7.4, max(t_hi) + 0.3))
    _band(ax, 5, 7, "цель ГДД")
    for x, label, style in ((lo_m, "быстро", ":"), (sum(times) / n, "середина", "--"),
                            (hi_m, "медленно", ":")):
        ax.axvline(x, color=P.TEXT_SECONDARY, lw=1.5, ls=style, zorder=4)
        ax.text(x, ax.get_ylim()[1] * 0.72, f" {label}\n {x:.1f} мин",
                color=P.TEXT_SECONDARY, fontsize=9)

    fig.text(0.045, 0.018,
             f"Все {n} этажей прошли проверку · "
             f"среднее число попыток генерации {sum(attempts)/n:.2f}",
             color=P.TEXT_MUTED, fontsize=9.5)
    fig.tight_layout(rect=(0.02, 0.035, 0.99, 0.945))
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path
