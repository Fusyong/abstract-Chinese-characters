# -*- coding: utf-8 -*-
"""由笔画轮廓求中线，再简化成折线。"""

from __future__ import annotations

import math
from collections import deque

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import distance_transform_edt

from measure.contours import Contour


def _raster(poly: list[tuple[float, float]], scale: float = 3.0, pad: int = 4):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    width = int(math.ceil((maxx - minx) * scale)) + pad * 2 + 2
    height = int(math.ceil((maxy - miny) * scale)) + pad * 2 + 2
    img = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(img)
    pix = [((x - minx) * scale + pad, (maxy - y) * scale + pad) for x, y in poly]
    draw.polygon(pix, outline=1, fill=1)
    mask = np.asarray(img, dtype=np.uint8)
    return mask, (minx, maxy, scale, pad)


def _pix_to_font(px: float, py: float, origin) -> tuple[float, float]:
    minx, maxy, scale, pad = origin
    return (minx + (px - pad) / scale, maxy - (py - pad) / scale)


def zhang_suen(mask: np.ndarray) -> np.ndarray:
    """Zhang-Suen 细化。用数组运算，避免逐像素的 Python 循环。"""
    img = np.pad((mask > 0).astype(np.uint8), 1, constant_values=0)
    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            p2 = img[:-2, 1:-1]
            p3 = img[:-2, 2:]
            p4 = img[1:-1, 2:]
            p5 = img[2:, 2:]
            p6 = img[2:, 1:-1]
            p7 = img[2:, :-2]
            p8 = img[1:-1, :-2]
            p9 = img[:-2, :-2]
            center = img[1:-1, 1:-1]
            total = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9
            ring = (p2, p3, p4, p5, p6, p7, p8, p9, p2)
            transitions = np.zeros_like(center)
            for i in range(8):
                transitions += (ring[i] == 0) & (ring[i + 1] == 1)
            kill = (center == 1) & (total >= 2) & (total <= 6) & (transitions == 1)
            if step == 0:
                kill &= (p2 * p4 * p6 == 0) & (p4 * p6 * p8 == 0)
            else:
                kill &= (p2 * p4 * p8 == 0) & (p2 * p6 * p8 == 0)
            if np.any(kill):
                changed = True
                center[kill] = 0
    return img[1:-1, 1:-1]


def _neighbors(y: int, x: int, img: np.ndarray):
    h, w = img.shape
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and img[ny, nx]:
                yield ny, nx


def _longest_path(img: np.ndarray) -> list[tuple[int, int]]:
    ys, xs = np.nonzero(img)
    if len(ys) == 0:
        return []
    nodes = list(zip(ys.tolist(), xs.tolist()))
    adj: dict[tuple[int, int], list[tuple[int, int]]] = {n: [] for n in nodes}
    for y, x in nodes:
        for nb in _neighbors(y, x, img):
            adj[(y, x)].append(nb)

    def bfs(start: tuple[int, int]):
        prev = {start: None}
        q = deque([start])
        last = start
        while q:
            last = q.popleft()
            for nb in adj[last]:
                if nb not in prev:
                    prev[nb] = last
                    q.append(nb)
        path = []
        cur = last
        while cur is not None:
            path.append(cur)
            cur = prev[cur]
        path.reverse()
        return last, path

    start = nodes[0]
    far, _ = bfs(start)
    _end, path = bfs(far)
    return [(x, y) for y, x in path]


def rdp(points: list[tuple[float, float]], epsilon: float) -> list[tuple[float, float]]:
    if len(points) < 3:
        return points
    start, end = points[0], points[-1]
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy) or 1.0
    worst_i = 0
    worst = -1.0
    for i, (x, y) in enumerate(points[1:-1], start=1):
        dist = abs((x - start[0]) * dy - (y - start[1]) * dx) / length
        if dist > worst:
            worst = dist
            worst_i = i
    if worst > epsilon:
        left = rdp(points[: worst_i + 1], epsilon)
        right = rdp(points[worst_i:], epsilon)
        return left[:-1] + right
    return [start, end]


def _turn_deg(a, b, c) -> float:
    v1 = (b[0] - a[0], b[1] - a[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    ang = math.degrees(math.atan2(v2[1], v2[0]) - math.atan2(v1[1], v1[0]))
    while ang <= -180:
        ang += 360
    while ang > 180:
        ang -= 360
    return ang


def centerline_of(contour: Contour, epsilon: float = 2.2) -> list[tuple[float, float]]:
    mask, origin = _raster(contour.polygon)
    # 太细的笔画先略膨胀，避免细化时断开。
    if mask.sum() < 8:
        return _fallback_line(contour)
    skel = zhang_suen(mask)
    if skel.sum() < 2:
        # 距离变换脊线作后备，再细化一次。
        dt = distance_transform_edt(mask)
        ridge = (dt >= 1.0).astype(np.uint8)
        skel = zhang_suen(ridge)
    path = _longest_path(skel)
    if len(path) < 2:
        return _fallback_line(contour)
    font_pts = [_pix_to_font(px + 0.5, py + 0.5, origin) for px, py in path]
    simplified = collapse_short(rdp(font_pts, epsilon), min_len=18.0)
    return simplified


def _fallback_line(contour: Contour) -> list[tuple[float, float]]:
    return [
        (contour.x_min, (contour.y_min + contour.y_max) / 2),
        (contour.x_max, (contour.y_min + contour.y_max) / 2),
    ]


# 短于这个长度的起笔、收笔算端头：中线保留，归类时不拿它单独当折。
STUB_LEN = 18.0


def collapse_short(pts: list[tuple[float, float]], min_len: float = STUB_LEN) -> list[tuple[float, float]]:
    """合并过短的中间碎段。起笔、收笔的端头保留。"""
    pts = [tuple(p) for p in pts]
    for _ in range(24):
        if len(pts) <= 3:
            break
        lengths = [
            math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
            for i in range(len(pts) - 1)
        ]
        internal = range(1, len(lengths) - 1)
        i = min(internal, key=lambda k: lengths[k])
        if lengths[i] >= min_len:
            break
        del pts[i + 1]
    return pts


def segment_info(pts: list[tuple[float, float]]) -> tuple[list[dict], list[float]]:
    segments = []
    for a, b in zip(pts, pts[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        angle = math.degrees(math.atan2(dy, dx))
        segments.append(
            {
                "dx": round(dx, 2),
                "dy": round(dy, 2),
                "length": round(length, 2),
                "angle": round(angle, 1),
            }
        )
    turns = []
    for i in range(1, len(pts) - 1):
        if segments[i - 1]["length"] < 8 or segments[i]["length"] < 8:
            continue
        turns.append(round(_turn_deg(pts[i - 1], pts[i], pts[i + 1]), 1))
    return segments, turns
