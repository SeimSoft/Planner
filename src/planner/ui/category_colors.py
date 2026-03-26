from __future__ import annotations

import hashlib

from PySide6.QtGui import QColor


def category_color(category: str) -> QColor:
    text = (category or "").strip().lower() or "uncategorized"
    digest = hashlib.sha1(text.encode("utf-8", errors="ignore")).digest()

    hue = int.from_bytes(digest[0:2], "big") % 360
    saturation = 120 + (digest[2] % 70)
    value = 150 + (digest[3] % 60)
    return QColor.fromHsv(hue, saturation, value)


def category_color_hex(category: str) -> str:
    return category_color(category).name()


def category_light_color(category: str, mix_to_white: float = 0.80) -> QColor:
    base = category_color(category)
    ratio = min(0.95, max(0.0, mix_to_white))
    red = int(base.red() + (255 - base.red()) * ratio)
    green = int(base.green() + (255 - base.green()) * ratio)
    blue = int(base.blue() + (255 - base.blue()) * ratio)
    return QColor(red, green, blue)


def category_light_color_hex(category: str, mix_to_white: float = 0.80) -> str:
    return category_light_color(category, mix_to_white=mix_to_white).name()


def contrast_text_color(background: QColor) -> str:
    luminance = (0.299 * background.red()) + (0.587 * background.green()) + (0.114 * background.blue())
    return "#0f172a" if luminance >= 160 else "#ffffff"
