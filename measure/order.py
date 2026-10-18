# -*- coding: utf-8 -*-
"""把轮廓归到笔顺编号，并按总表的笔顺串排列。

笔顺编号（与总表末位数字一致）：
1 横，2 竖，3 撇，4 点或捺，5 折。

同号笔画的先后、部件的先后、一笔的起笔和收笔，都用同一条斜线。
斜线只比较中线的端点。见 sweep_key。
"""

from __future__ import annotations

import math
from collections import Counter

from measure.centerline import STUB_LEN, _turn_deg, centerline_of, segment_info
from measure.contours import Contour

CODE_NAME = {"1": "横", "2": "竖", "3": "撇", "4": "点", "5": "折"}

# 中线保留端头。短端头上的弯折不单独算成折；笔身转角达到该值才视为折。
FOLD_TURN = 50.0


def _fold_name(segments: list[dict], turns: list[float]) -> str:
    big = [t for t in turns if abs(t) >= FOLD_TURN]
    if not segments:
        return "折"
    last = segments[-1]["angle"]
    if len(big) >= 2 and last > 90:
        return "横折钩"
    if abs(last + 90) < 30:
        return "横折"
    if last < -110:
        return "横撇"
    return "折"


def _length(pts: list[tuple[float, float]]) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))


def _body_span(segments: list[dict]) -> tuple[int, int]:
    """笔身所在的段下标。两端短于一笔宽度的端头剥开，点本身只有一段时不剥。"""
    start, end = 0, len(segments)
    while end - start > 1 and segments[start]["length"] < STUB_LEN:
        start += 1
    while end - start > 1 and segments[end - 1]["length"] < STUB_LEN:
        end -= 1
    return start, end


def _body_ends(pts: list[tuple[float, float]], segments: list[dict]):
    start, end = _body_span(segments)
    return pts[start], pts[end]


def _body_turns(pts: list[tuple[float, float]], segments: list[dict]) -> list[float]:
    start, end = _body_span(segments)
    turns = []
    for i in range(start + 1, end):
        if segments[i - 1]["length"] < 8 or segments[i]["length"] < 8:
            continue
        turns.append(round(_turn_deg(pts[i - 1], pts[i], pts[i + 1]), 1))
    return turns


def _horizontality(angle: float) -> float:
    a = abs(angle) % 180
    return min(a, 180 - a)


def _seg_angle(a, b) -> float:
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def orient_shape(pts: list[tuple[float, float]], code: str) -> list[tuple[float, float]]:
    """按笔身定一个朝向，只用来判断类别和名称。起笔收笔另由斜线决定。"""
    if len(pts) < 2:
        return list(pts)
    segments, _ = segment_info(pts)
    if code == "5":
        start, end = _body_span(segments)
        forward = _horizontality(_seg_angle(pts[start], pts[start + 1]))
        backward = _horizontality(_seg_angle(pts[end], pts[end - 1]))
        if backward + 8 < forward:
            pts = list(reversed(pts))
            segments, _ = segment_info(pts)
            start, end = _body_span(segments)
        ang = _seg_angle(pts[start], pts[start + 1])
        if abs(abs(ang) - 180) < abs(ang):
            pts = list(reversed(pts))
        return pts
    start, end = _body_ends(pts, segments)
    if code == "1":
        if end[0] < start[0]:
            return list(reversed(pts))
        return list(pts)
    if end[1] > start[1]:
        return list(reversed(pts))
    return list(pts)


def _endpoint_code(pts: list[tuple[float, float]], contour: Contour) -> str:
    """没有明显转角时，用笔身走向归入横竖撇点。"""
    if contour.height < contour.width * 0.42:
        return "1"
    segments, _ = segment_info(pts)
    start, end = _body_ends(pts, segments)
    if end[1] > start[1]:
        start, end = end, start
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    if abs(dy) < 1:
        return "1"
    if abs(dx) <= abs(dy) * 0.28 and contour.width < contour.height * 0.55:
        return "2"
    if dx < 0:
        return "3"
    return "4"


def measure_contour(contour: Contour, raw: list[tuple[float, float]] | None = None) -> None:
    if raw is None:
        raw = centerline_of(contour)
    segments, _ = segment_info(raw)
    folded = any(abs(t) >= FOLD_TURN for t in _body_turns(raw, segments))
    code = "5" if folded else _endpoint_code(raw, contour)
    shaped = orient_shape(raw, code)
    segments, _ = segment_info(shaped)
    name = CODE_NAME[code]
    if code == "4":
        name = "点" if _length(shaped) < 55 else "捺"
    elif code == "5":
        span = _body_span(segments)
        name = _fold_name(segments[span[0] : span[1]], _body_turns(shaped, segments))
    directed = direct_by_sweep(shaped)
    segments, turns = segment_info(directed)
    contour.code = code
    contour.name = name
    contour.centerline = [(round(x, 2), round(y, 2)) for x, y in directed]
    contour.segments = segments
    contour.turns = turns


# 斜线自左下走向右上，再往右下平移，先碰到的先写。
# 这是右手小臂以下的活动方式：手往右下伸最顺，所以先碰到的端点先落笔。
# 右下方向与水平的夹角。字体坐标 y 向上，方位角是这个角的负值。
# 只比较中线的两个端点。折线转折点先不参加，特殊情况以后再说。
# 三层用同一条规则：起笔收笔比两个端点，笔画比各笔的起笔，
# 部件比该部件各笔端点里最先碰到的那个。纯字形的部件拆分还没有。
# 端点比较、并用笔顺动画核对之后，53° 到 54° 能同时排对永、川、看、拜、沙、堂、学。
# 环差在部件：王的底横和不的横都是横，还没按部件分开时会插队。暂取 54°。
SWEEP_DEPRESSION_DEG = 54.0
SWEEP_BEARING_DEG = -SWEEP_DEPRESSION_DEG
_SWEEP_DX = math.cos(math.radians(SWEEP_BEARING_DEG))
_SWEEP_DY = math.sin(math.radians(SWEEP_BEARING_DEG))


def set_sweep_depression(deg: float) -> None:
    """换右下方向与水平的夹角。测阈值时用，测完要设回选定的角度。"""
    global SWEEP_DEPRESSION_DEG, SWEEP_BEARING_DEG, _SWEEP_DX, _SWEEP_DY
    SWEEP_DEPRESSION_DEG = deg
    SWEEP_BEARING_DEG = -deg
    _SWEEP_DX = math.cos(math.radians(SWEEP_BEARING_DEG))
    _SWEEP_DY = math.sin(math.radians(SWEEP_BEARING_DEG))


def touch_value(points: list[tuple[float, float]]) -> float:
    """这些端点里，斜线最先碰到的投影。越小越先写。"""
    return min(x * _SWEEP_DX + y * _SWEEP_DY for x, y in points)


def _endpoints(contour: Contour) -> list[tuple[float, float]]:
    if len(contour.centerline) >= 2:
        return [contour.centerline[0], contour.centerline[-1]]
    if contour.centerline:
        return [contour.centerline[0]]
    return [(contour.x_min, contour.y_max)]


def direct_by_sweep(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """动作层：两个端点里先碰到的一端作起笔。"""
    if len(pts) < 2:
        return list(pts)
    start = pts[0][0] * _SWEEP_DX + pts[0][1] * _SWEEP_DY
    finish = pts[-1][0] * _SWEEP_DX + pts[-1][1] * _SWEEP_DY
    if start <= finish:
        return list(pts)
    return list(reversed(pts))


def sweep_key(contour: Contour) -> tuple[float, float]:
    """笔画层：起笔先被碰到的笔画键更小。第二项只在投影相同时取更靠左的起笔。"""
    ends = _endpoints(contour)
    return (touch_value(ends), ends[0][0])


def component_touch(contours: list[Contour]) -> float:
    """部件层：该部件各笔端点里，斜线最先碰到的投影。"""
    points = [p for contour in contours for p in _endpoints(contour)]
    return touch_value(points)


def match_codes(contours: list[Contour], codes: str) -> list[Contour] | None:
    """用五类编号对齐总表笔顺。编号多重集不一致时无解。"""
    if len(contours) != len(codes):
        return None
    if Counter(c.code for c in contours) != Counter(codes):
        return None
    remaining = set(range(len(contours)))
    chosen: list[Contour] = []
    for code in codes:
        candidates = [i for i in remaining if contours[i].code == code]
        best = min(candidates, key=lambda i: sweep_key(contours[i]))
        chosen.append(contours[best])
        remaining.remove(best)
    return chosen
