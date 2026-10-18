# -*- coding: utf-8 -*-
"""从 TrueType 字形取出逐笔画闭合轮廓。"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont

# 这套楷体每个字共用的字形框（y 向上）。
EM_BOX = (0.0, -36.0, 256.0, 220.0)


def _flatness(p0, p1, p2) -> float:
    dx = p2[0] - p0[0]
    dy = p2[1] - p0[1]
    length = math.hypot(dx, dy) or 1.0
    return abs((p1[0] - p0[0]) * dy - (p1[1] - p0[1]) * dx) / length


def flatten_quadratic(p0, p1, p2, tol: float = 0.35) -> list[tuple[float, float]]:
    if _flatness(p0, p1, p2) <= tol:
        return [p2]
    a = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
    b = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
    m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    return flatten_quadratic(p0, a, m, tol) + flatten_quadratic(m, b, p2, tol)


def flatten_cubic(p0, p1, p2, p3, tol: float = 0.35) -> list[tuple[float, float]]:
    dx = p3[0] - p0[0]
    dy = p3[1] - p0[1]
    length = math.hypot(dx, dy) or 1.0
    d1 = abs((p1[0] - p0[0]) * dy - (p1[1] - p0[1]) * dx) / length
    d2 = abs((p2[0] - p0[0]) * dy - (p2[1] - p0[1]) * dx) / length
    if max(d1, d2) <= tol:
        return [p3]
    p01 = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
    p12 = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
    p23 = ((p2[0] + p3[0]) / 2, (p2[1] + p3[1]) / 2)
    p012 = ((p01[0] + p12[0]) / 2, (p01[1] + p12[1]) / 2)
    p123 = ((p12[0] + p23[0]) / 2, (p12[1] + p23[1]) / 2)
    mid = ((p012[0] + p123[0]) / 2, (p012[1] + p123[1]) / 2)
    return flatten_cubic(p0, p01, p012, mid, tol) + flatten_cubic(mid, p123, p23, p3, tol)


class FlattenPen(BasePen):
    def __init__(self, glyph_set) -> None:
        super().__init__(glyph_set)
        self.contours: list[list[tuple[float, float]]] = []
        self._pts: list[tuple[float, float]] = []

    def _moveTo(self, pt) -> None:
        self._pts = [(float(pt[0]), float(pt[1]))]

    def _lineTo(self, pt) -> None:
        self._pts.append((float(pt[0]), float(pt[1])))

    def _curveToOne(self, p1, p2, p3) -> None:
        self._pts.extend(
            flatten_cubic(self._pts[-1], tuple(p1), tuple(p2), tuple(p3))
        )

    def _qCurveToOne(self, p1, p2) -> None:
        self._pts.extend(flatten_quadratic(self._pts[-1], tuple(p1), tuple(p2)))

    def _closePath(self) -> None:
        if len(self._pts) >= 3:
            self.contours.append(self._pts)
        self._pts = []

    def _endPath(self) -> None:
        if len(self._pts) >= 3:
            self.contours.append(self._pts)
        self._pts = []


@dataclass
class Contour:
    index: int
    polygon: list[tuple[float, float]]
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    svg: str = ""
    code: str = ""
    name: str = ""
    centerline: list[tuple[float, float]] = field(default_factory=list)
    segments: list[dict] = field(default_factory=list)
    turns: list[float] = field(default_factory=list)

    @property
    def width(self) -> float:
        return self.x_max - self.x_min

    @property
    def height(self) -> float:
        return self.y_max - self.y_min


def polygon_to_svg(pts: list[tuple[float, float]]) -> str:
    if not pts:
        return ""
    parts = [f"M{pts[0][0]:.2f} {pts[0][1]:.2f}"]
    prev = pts[0]
    for x, y in pts[1:]:
        if abs(x - prev[0]) < 0.05 and abs(y - prev[1]) < 0.05:
            continue
        parts.append(f"L{x:.2f} {y:.2f}")
        prev = (x, y)
    parts.append("Z")
    return "".join(parts)


def load_font(path) -> TTFont:
    return TTFont(path)


def glyph_contours(font: TTFont, char: str) -> list[Contour]:
    cmap = font.getBestCmap()
    cp = ord(char)
    if cp not in cmap:
        raise KeyError(f"字体中无字符：{char}")
    glyph_set = font.getGlyphSet()
    pen = FlattenPen(glyph_set)
    glyph_set[cmap[cp]].draw(pen)
    contours: list[Contour] = []
    for i, poly in enumerate(pen.contours):
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        contours.append(
            Contour(
                index=i,
                polygon=poly,
                x_min=min(xs),
                y_min=min(ys),
                x_max=max(xs),
                y_max=max(ys),
                svg=polygon_to_svg(poly),
            )
        )
    return contours
