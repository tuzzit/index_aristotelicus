#!/usr/bin/env python3
"""把 ../split_out/ 的掃描圖塊壓成 4 階灰度 PNG，放進 scans/ 供 cloud session 對照。

原圖每頁約 3 MB；4 階灰度約 0.9 MB，字形與重音、氣息符肉眼無差別。
只能在本機執行 (需要 ../split_out/)。

用法: python3 tools/export_scans.py 58-107        (已存在者略過)
"""
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT.parent / "split_out"
OUT = ROOT / "scans"


def main():
    a, _, b = sys.argv[1].partition("-")
    OUT.mkdir(exist_ok=True)
    n = 0
    for p in range(int(a), int(b or a) + 1):
        for f in sorted(SRC.glob(f"page-{p:03d}_*.png")):
            dst = OUT / f.name
            if dst.exists():
                continue
            Image.open(f).convert("L").quantize(4).save(dst, optimize=True)
            n += 1
    print(f"{n} 個圖塊 → {OUT}")


if __name__ == "__main__":
    main()
