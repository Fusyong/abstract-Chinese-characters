# -*- coding: utf-8 -*-
"""读取《拼字游戏汉字信息总表》里的笔顺编号。"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CharInfo:
    char: str
    stroke_count: int
    codes: str
    structure: str
    radical: str


def load_catalog(path: Path) -> dict[str, CharInfo]:
    table: dict[str, CharInfo] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            char = row["字"]
            count = int(row["笔画数"] or 0)
            raw = (row["笔顺"] or "").strip()
            codes = raw[-count:] if count else ""
            table[char] = CharInfo(
                char=char,
                stroke_count=count,
                codes=codes,
                structure=row.get("结构") or "",
                radical=row.get("部首") or "",
            )
    return table
