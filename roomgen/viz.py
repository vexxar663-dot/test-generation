"""Визуализация этажа на matplotlib.

Три фигуры:
  figure_floor  — один этаж крупно: карта, легенда, счётчики, тайминг;
  figure_sheet  — лист из нескольких сидов (проверка разнообразия «на глаз»);
  figure_stats  — распределения по N этажам против требований ГДД.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable, List, Optional, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch

from . import palette as P
from .config import GLYPH, RU_NAME, RoomType
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

_GAP = 0.16  # зазор между комнатами: в нём видны двери


def _xy(cell):
    """Клетка (row, col) → центр в координатах осей (y вниз)."""
    r, c = cell
    return c + 0.5, -(r + 0.5)


def draw_floor(ax, floor: Floor, show_empty: bool = True, glyph_size: float = 13.0) -> None:
    """Нарисовать сетку, двери и подсветку критического пути на осях ax."""
    cfg = floor.config
    ax.set_xlim(-0.15, cfg.width + 0.15)
    ax.set_ylim(-cfg.height - 0.15, 0.15)
    ax.set_aspect("equal")
    ax.axis("off")

    # 1. Критический путь — ахроматическая «подсветка» ПОД комнатами:
    #    в зазорах между клетками видно, каким коридором игрок обязан пройти.
    crit = floor.critical_path()
    if len(crit) > 1:
        xs, ys = zip(*(_xy(c) for c in crit))
        ax.plot(xs, ys, color=P.PATH_COLOR, lw=9.0, alpha=0.30,
                solid_capstyle="round", solid_joinstyle="round", zorder=1)

    # 2. Двери — тонкие перемычки в зазоре.
    for door in floor.doors:
        a, b = sorted(door)
        (ax1, ay1), (ax2, ay2) = _xy(a), _xy(b)
        on_crit = a in crit and b in crit and abs(crit.index(a) - crit.index(b)) == 1
        ax.plot([ax1, ax2], [ay1, ay2],
                color=P.PATH_COLOR if on_crit else P.DOOR_COLOR,
                lw=2.4 if on_crit else 1.6, zorder=2,
                solid_capstyle="round")

    # 3. Комнаты.
    for r in range(cfg.height):
        for c in range(cfg.width):
            cell = (r, c)
            t = floor.type_at(cell)
            if t is RoomType.EMPTY and not show_empty:
                continue
            st = P.STYLES[t]
            x, y = c + _GAP / 2, -(r + 1) + _GAP / 2
            size = 1 - _GAP
            box = FancyBboxPatch(
                (x, y), size, size,
                boxstyle="round,pad=0,rounding_size=0.09",
                facecolor=st.fill, edgecolor=st.edge, linewidth=st.lw,
                linestyle=":" if t is RoomType.EMPTY else "-",
                zorder=3,
            )
            ax.add_patch(box)
            if t is not RoomType.EMPTY:
                cx, cy = _xy(cell)
                ax.text(cx, cy, GLYPH[t], ha="center", va="center",
                        color=st.ink, fontsize=glyph_size, fontweight="bold", zorder=4)


def _legend_handles() -> List[Line2D]:
    handles = []
    for t in P.LEGEND_ORDER:
        st = P.STYLES[t]
        handles.append(Line2D(
            [], [], marker="s", linestyle="none", markersize=9,
            markerfacecolor=st.fill, markeredgecolor=st.edge, markeredgewidth=1.4,
            label=f"{GLYPH[t]}  {RU_NAME[t]}",
        ))
    handles.append(Line2D([], [], color=P.PATH_COLOR, lw=2.4,
                          label="путь спавн → босс"))
    handles.append(Line2D([], [], color=P.DOOR_COLOR, lw=1.6, label="дверь"))
    return handles


def figure_floor(floor: Floor, path: str) -> str:
    """Один этаж крупно: карта + легенда + сводка."""
    fig = plt.figure(figsize=(12.2, 6.6))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 1.05], wspace=0.02,
                          left=0.035, right=0.98, top=0.85, bottom=0.04)
    ax_map = fig.add_subplot(gs[0, 0])
    draw_floor(ax_map, floor)

    fig.text(0.035, 0.94, "Equation Dodge — генерация этажа",
             color=P.TEXT_PRIMARY, fontsize=18, fontweight="bold")
    crit = floor.critical_path()
    fig.text(0.035, 0.895,
             f"seed {floor.seed} · сетка {floor.config.height}×{floor.config.width} · "
             f"{len(floor.rooms())} комнат · {len(floor.doors)} дверей · "
             f"путь до босса {len(crit)} комнат",
             color=P.TEXT_MUTED, fontsize=11)

    ax_side = fig.add_subplot(gs[0, 1])
    ax_side.axis("off")
    ax_side.legend(handles=_legend_handles(), loc="upper left", frameon=False,
                   labelspacing=0.78, handletextpad=0.9, fontsize=10.5,
                   labelcolor=P.TEXT_SECONDARY, ncol=1,
                   bbox_to_anchor=(-0.02, 1.02))

    counts = floor.counts()
    lines = ["СОСТАВ ЭТАЖА"]
    for t in P.LEGEND_ORDER:
        n = counts.get(t, 0)
        lo, hi = floor.config.caps.get(t, (0, 0))
        flag = "" if lo <= n <= hi else "  ← вне лимита"
        lines.append(f"{RU_NAME[t]:<14} {n}   (ГДД {lo}–{hi}){flag}")
    lo_all, hi_all = floor.time_estimate()
    lo_cr, hi_cr = floor.time_estimate(crit)
    lines += [
        "",
        "ТАЙМИНГ (ГДД: 5–7 мин на этаж)",
        f"только до босса   {lo_cr/60:.1f}–{hi_cr/60:.1f} мин",
        f"зачистка на 100%  {lo_all/60:.1f}–{hi_all/60:.1f} мин",
    ]
    ax_side.text(0.47, 1.02, "\n".join(lines), transform=ax_side.transAxes,
                 va="top", ha="left", fontsize=10.5, color=P.TEXT_SECONDARY,
                 family="DejaVu Sans Mono", linespacing=1.7)

    ax_side.text(
        -0.02, 0.30,
        "ЦВЕТ = КЛАСС, ГЛИФ = ТИП\n"
        "жёлтый — награда (сундук, ивент)\n"
        "аква — сервис (столовая, толчок)\n"
        "фиолетовый — риск (ставка на сложность)\n"
        "серый/белый — каркас этажа\n\n"
        "Лестница соединена только с боссом:\n"
        "на следующий этаж — лишь через боссфайт.",
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
    fig, axes = plt.subplots(rows, cols, figsize=(3.1 * cols, 3.95 * rows))
    axes = axes.ravel() if hasattr(axes, "ravel") else [axes]
    for ax, floor in zip(axes, floors):
        draw_floor(ax, floor, glyph_size=9.0)
        counts = floor.counts()
        extras = "".join(GLYPH[t] for t in
                         (RoomType.CHEST, RoomType.CAFETERIA, RoomType.TOILET,
                          RoomType.EVENT, RoomType.HARD)
                         for _ in range(counts.get(t, 0)))
        ax.set_title(f"seed {floor.seed} · {len(floor.rooms())} комнат  {extras}",
                     color=P.TEXT_SECONDARY, fontsize=9.5, pad=6)
    for ax in axes[len(floors):]:
        ax.axis("off")
    fig.suptitle("Разнообразие планировок по сидам", color=P.TEXT_PRIMARY,
                 fontsize=15, fontweight="bold", y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.96), h_pad=3.2)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _band(ax, lo, hi, label):
    """Серая полоса «требование ГДД» за данными."""
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
    totals, path_len, times, crit_len = [], [], [], []
    t_lo, t_hi, forced = [], [], []
    #: Тайловая метрика считается дольше — берём подвыборку.
    forced_sample = min(n, 400)
    type_counts: Counter = Counter()
    presence: Counter = Counter()
    attempts = []
    for seed in range(n):
        floor = generate(seed, cfg)
        totals.append(len(floor.rooms()))
        path_len.append(len(floor.main_path))
        crit_len.append(len(floor.critical_path()))
        if seed < forced_sample:
            from . import tilemap as _T

            forced.append(_T.rooms_to_boss(floor, _T.build(floor)) + 1)
        attempts.append(floor.attempts)
        lo, hi = floor.time_estimate()
        t_lo.append(lo / 60)
        t_hi.append(hi / 60)
        times.append((lo + hi) / 2 / 60)
        for t, c in floor.counts().items():
            type_counts[t] += c
            presence[t] += 1

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
    ax.vlines(mean_total, 0, top * 1.06, color=P.TEXT_SECONDARY, lw=1.6,
              ls="--", zorder=4)
    ax.text(mean_total, top * 0.72, f" факт {mean_total:.1f}",
            color=P.TEXT_SECONDARY, fontsize=9.5)

    # 2. Сколько комнат игрок обязан пройти (по тайлам школьной планировки).
    ax = axes[0, 1]
    sample = len(forced)
    vals = sorted(Counter(forced).items())
    ax.bar([v for v, _ in vals], [c / sample * 100 for _, c in vals],
           color=P.CHART_HUE, width=0.72, zorder=3)
    ax.set_ylabel("% этажей", fontsize=10)
    ax.set_ylim(0, max(c / sample * 100 for _, c in vals) * 1.25)
    _style_axes(ax, "Комнат обязательно пройти до босса",
                f"мимо остальных можно пройти коридором · выборка {sample} этажей")
    _band(ax, 4.5, 6.5, "ГДД 3.1: 5–6 комнат")

    # 3. Состав этажа.
    ax = axes[1, 0]
    order = [t for t in P.LEGEND_ORDER]
    means = [type_counts[t] / n for t in order]
    ypos = range(len(order))
    ax.barh(list(ypos), means, color=[P.STYLES[t].edge for t in order],
            height=0.66, zorder=3)
    ax.set_yticks(list(ypos))
    ax.set_yticklabels([RU_NAME[t] for t in order], fontsize=9.5)
    ax.invert_yaxis()
    for i, (t, m) in enumerate(zip(order, means)):
        share = presence[t] / n * 100
        ax.text(m + 0.12, i, f"{m:.2f}   (есть на {share:.0f}% этажей)",
                va="center", fontsize=9, color=P.TEXT_SECONDARY)
    ax.set_xlim(0, max(means) * 1.62)
    _style_axes(ax, "Среднее число комнат каждого типа", "комнат на этаж")
    ax.grid(axis="y", visible=False)

    # 4. Время этажа: середина оценки + средние границы «быстро/медленно».
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
             f"Все {n} этажей прошли проверку шага 8 · "
             f"среднее число попыток генерации {sum(attempts)/n:.2f}",
             color=P.TEXT_MUTED, fontsize=9.5)
    fig.tight_layout(rect=(0.02, 0.035, 0.99, 0.945))
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path
