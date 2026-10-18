# -*- coding: utf-8 -*-
"""笔顺动画分笔图。只在五类编号对不上总表时用来排笔顺。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from measure.contours import Contour

ROOT = Path(__file__).resolve().parents[1]
ANIMATION_ROOT = ROOT / "资料" / "笔顺动画" / "H5工程" / "工程"

# 分到某一张动画图上的重叠低于这个值，就不当作对上了。
MIN_IOU = 0.4


def animation_dir(char: str) -> Path | None:
    folder = ANIMATION_ROOT / char
    if folder.is_dir() and any(folder.glob("stroke_*.png")):
        return folder
    return None


def _pngs(folder: Path) -> list[Path]:
    files = list(folder.glob("stroke_*.png"))
    files.sort(key=lambda path: int(path.stem.rsplit("_", 1)[-1]))
    return files


def _mask(path: Path) -> np.ndarray:
    image = Image.open(path).convert("L")
    return np.asarray(image) > 127


def _ink_bbox(mask: np.ndarray):
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def _render(contour: Contour, origin, size: int, scale: float) -> np.ndarray:
    minx, maxy = origin
    img = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(img)
    pix = [((x - minx) * scale, (maxy - y) * scale) for x, y in contour.polygon]
    draw.polygon(pix, fill=255)
    return np.asarray(img) > 0


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    return float(inter) / float(union) if union else 0.0


def order_by_animation(char: str, contours: list[Contour]) -> tuple[list[Contour] | None, dict]:
    """按与分笔图的重叠，把轮廓排成动画里的书写顺序。"""
    folder = animation_dir(char)
    if folder is None:
        return None, {"ok": False, "reason": "没有笔顺动画分笔图"}
    masks = [_mask(path) for path in _pngs(folder)]
    if len(masks) != len(contours):
        return None, {
            "ok": False,
            "reason": f"分笔图 {len(masks)} 张，轮廓 {len(contours)} 个",
        }
    union = np.any(masks, axis=0)
    box = _ink_bbox(union)
    if box is None:
        return None, {"ok": False, "reason": "分笔图没有墨迹"}
    left, top, right, bottom = box
    font_left = min(c.x_min for c in contours)
    font_right = max(c.x_max for c in contours)
    font_bottom = min(c.y_min for c in contours)
    font_top = max(c.y_max for c in contours)
    png_w = max(right - left, 1)
    png_h = max(bottom - top, 1)
    scale = ((png_w / max(font_right - font_left, 1)) + (png_h / max(font_top - font_bottom, 1))) / 2
    origin = (font_left - left / scale, font_top + top / scale)
    size = int(masks[0].shape[0])
    rendered = [_render(contour, origin, size, scale) for contour in contours]

    pairs: list[tuple[float, int, int]] = []
    for i, glyph in enumerate(rendered):
        for j, ref in enumerate(masks):
            pairs.append((_iou(glyph, ref), i, j))
    pairs.sort(reverse=True)
    used_contour: set[int] = set()
    used_frame: set[int] = set()
    assigned = [-1] * len(contours)
    ious = [0.0] * len(contours)
    for score, contour_i, frame_j in pairs:
        if contour_i in used_contour or frame_j in used_frame:
            continue
        used_contour.add(contour_i)
        used_frame.add(frame_j)
        assigned[frame_j] = contour_i
        ious[frame_j] = round(score, 3)
        if len(used_contour) == len(contours):
            break
    if min(ious) < MIN_IOU or -1 in assigned:
        return None, {"ok": False, "reason": "分笔图对不上轮廓", "iou": ious}
    ordered = [contours[index] for index in assigned]
    return ordered, {
        "ok": True,
        "source": str(folder.relative_to(ROOT)).replace("\\", "/"),
        "iou": ious,
    }
