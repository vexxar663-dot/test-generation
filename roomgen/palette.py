"""Палитра карты этажа.

Следует цветовой философии ГДД («ахроматическая база + акцентные цвета»):

* Каркас этажа — спавн, обычные комнаты, босс, лестница — БЕЗ цвета
  (чёрный/белый/серый). Их различают глиф, позиция и толщина обводки.
* Цвет несут только три класса точек интереса — их игрок ищет глазами:
    жёлтый  #c98500 — награда   (сундук, ивент-головоломка)
    аква    #199e70 — сервис    (столовая, толчок)
    фиолет. #9085e9 — риск      (усложнённая комната, ставка на сложность)
* Тип комнаты внутри класса всегда продублирован глифом и легендой, то есть
  цвет никогда не единственный носитель смысла.

Тройка акцентов проверена валидатором палитр на тёмной поверхности #1a1a19
в режиме «все пары» (на карте любые два типа могут оказаться рядом):
  CVD-разделение  худшая пара ΔE 8.4 (норма ≥ 8)
  обычное зрение  худшая пара ΔE 19.8 (порог ≥ 15)
  контраст к фону все ≥ 3:1
"""

from __future__ import annotations

from typing import Dict, NamedTuple

from .config import RoomType

# --- Поверхности и текст ---------------------------------------------------
SURFACE = "#1a1a19"
SURFACE_SUNKEN = "#161615"
TEXT_PRIMARY = "#ffffff"
TEXT_SECONDARY = "#c3c2b7"
TEXT_MUTED = "#8a887e"
GRID_LINE = "#2a2a27"

# --- Акценты (проверены валидатором) ---------------------------------------
ACCENT_REWARD = "#c98500"
ACCENT_SERVICE = "#199e70"
ACCENT_RISK = "#9085e9"

# --- Ахроматический каркас -------------------------------------------------
BONE = "#e8e6dd"
GRAY_ROOM = "#35352f"
GRAY_EDGE = "#6e6d66"
VOID = "#0f0f0e"

#: Единственный цвет для статистических графиков (одна серия — легенда не нужна).
CHART_HUE = "#3987e5"
CHART_BAND = "#2e2e2b"


class RoomStyle(NamedTuple):
    fill: str
    edge: str
    ink: str      # цвет глифа
    lw: float     # толщина обводки
    cls: str      # класс для легенды


STYLES: Dict[RoomType, RoomStyle] = {
    RoomType.SPAWN:     RoomStyle(BONE, BONE, "#0b0b0b", 1.6, "каркас"),
    RoomType.NORMAL:    RoomStyle(GRAY_ROOM, GRAY_EDGE, TEXT_SECONDARY, 1.2, "каркас"),
    RoomType.BOSS:      RoomStyle(VOID, BONE, BONE, 2.6, "каркас"),
    RoomType.STAIRS:    RoomStyle("#57564f", BONE, BONE, 1.6, "каркас"),
    RoomType.CHEST:     RoomStyle(ACCENT_REWARD, ACCENT_REWARD, "#0b0b0b", 1.2, "награда"),
    RoomType.EVENT:     RoomStyle(SURFACE, ACCENT_REWARD, ACCENT_REWARD, 2.2, "награда"),
    RoomType.CAFETERIA: RoomStyle(ACCENT_SERVICE, ACCENT_SERVICE, "#0b0b0b", 1.2, "сервис"),
    RoomType.TOILET:    RoomStyle(SURFACE, ACCENT_SERVICE, ACCENT_SERVICE, 2.2, "сервис"),
    RoomType.HARD:      RoomStyle(ACCENT_RISK, ACCENT_RISK, "#0b0b0b", 1.2, "риск"),
}

#: Порядок типов в легенде.
LEGEND_ORDER = (
    RoomType.SPAWN, RoomType.NORMAL, RoomType.BOSS, RoomType.STAIRS,
    RoomType.CHEST, RoomType.EVENT,
    RoomType.CAFETERIA, RoomType.TOILET,
    RoomType.HARD,
)

DOOR_COLOR = GRAY_EDGE
PATH_COLOR = BONE
