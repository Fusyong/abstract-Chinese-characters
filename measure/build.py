# -*- coding: utf-8 -*-
"""生成 web/data/strokes.json。

笔顺先用五类编号对齐总表。编号对不上时，才用笔顺动画的分笔图。
"""

from __future__ import annotations

import json
from pathlib import Path

from measure.catalog import load_catalog
from measure.contours import EM_BOX, glyph_contours, load_font
from measure.fallback import order_by_animation
from measure.order import match_codes, measure_contour

ROOT = Path(__file__).resolve().parents[1]
FONT_PATH = ROOT / "assets" / "kaiti_GB2312.ttf"
CSV_PATH = ROOT / "资料" / "拼字游戏汉字信息总表2022-10-14.csv"
OUT_PATH = ROOT / "web" / "data" / "strokes.json"

# 前十个覆盖基本笔画。后七个用来核对斜线角度。
SAMPLE = list("永一十人八口日月王木看拜环沙堂心学")

CODE_LABEL = {"1": "横", "2": "竖", "3": "撇", "4": "点或捺", "5": "折"}


def contour_record(contour, step: int) -> dict:
    return {
        "step": step,
        "contourIndex": contour.index,
        "code": contour.code,
        "codeLabel": CODE_LABEL[contour.code],
        "name": contour.name,
        "svg": contour.svg,
        "bbox": [
            round(contour.x_min, 2),
            round(contour.y_min, 2),
            round(contour.x_max, 2),
            round(contour.y_max, 2),
        ],
        "centerline": contour.centerline,
        "segments": contour.segments,
        "turns": contour.turns,
    }


def build() -> dict:
    font = load_font(FONT_PATH)
    catalog = load_catalog(CSV_PATH)
    characters = []
    for char in SAMPLE:
        info = catalog[char]
        contours = glyph_contours(font, char)
        for contour in contours:
            measure_contour(contour)
        ordered = match_codes(contours, info.codes)
        order_method = "codes"
        animation = None
        if ordered is None:
            ordered, animation = order_by_animation(char, contours)
            order_method = "animation"
        if ordered is None:
            got = "".join(c.code for c in contours)
            reason = f"笔画类别 {got or '—'} 对不上笔顺 {info.codes}"
            if animation and animation.get("reason"):
                reason += "；" + animation["reason"]
            characters.append(
                {
                    "char": char,
                    "ok": False,
                    "reason": reason,
                    "codes": info.codes,
                    "orderMethod": None,
                }
            )
            print(f"{char} 无解 {reason}")
            continue
        record = {
            "char": char,
            "ok": True,
            "codes": info.codes,
            "structure": info.structure,
            "radical": info.radical,
            "orderMethod": order_method,
            "strokes": [contour_record(c, i + 1) for i, c in enumerate(ordered)],
        }
        if order_method == "animation":
            record["animation"] = animation
        characters.append(record)
        names = "、".join(s["name"] for s in record["strokes"])
        print(f"{char} {info.codes} -> {names} [{order_method}]")

    payload = {
        "font": FONT_PATH.name,
        "unitsPerEm": font["head"].unitsPerEm,
        "emBox": list(EM_BOX),
        "strokeCodes": CODE_LABEL,
        "characters": characters,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT_PATH)
    return payload


def main() -> None:
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    payload = build()
    failed = [c for c in payload["characters"] if not c.get("ok")]
    if failed:
        print("未能排定：" + "、".join(c["char"] for c in failed))


if __name__ == "__main__":
    main()
