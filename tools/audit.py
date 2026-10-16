#!/usr/bin/env python3
"""全書結構化結果的自動檢查 → data/audit.tsv
  LEFT   用例文字中殘留未解析的出處
  NOWORK 出處無法對應作品
  RANGE  Bekker 頁碼不在該作品範圍 (多為 OCR 誤認縮寫或數字)
"""
import json, re, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import sigla as S

ROOT = Path(__file__).resolve().parents[1]
d = json.loads((ROOT / "data" / "entries.json").read_text(encoding="utf-8"))
rows = []
for e in d:
    src = "page-%03d" % e["src"]
    for n in e["body"]:
        for it in n.get("items", []):
            t = re.sub(r"\([^()]*\)|(?<![\w])p ?\d{1,3}\s?[ᵃᵇ]\d+|Schol \d+[ᵃᵇ]\d+", "", it["text"])
            if re.search(r"(?<![\w])[Α-Ωα-ω]{1,4}\d+\.\d|\d+[ᵃᵇ]\d|\b(?:Bz|Wz)\b", t):
                rows.append((src, "LEFT", e["lemma"], it["text"][:100]))
            for c in it["cites"]:
                if c.get("guess"):
                    rows.append((src, "GUESS", e["lemma"], f'{c["sig"]}{c["ch_eff"] or ""}.{c["page"]}{c["col"]}{c["line"]}'))
                if not c["work"]:
                    rows.append((src, "NOWORK", e["lemma"], f'{c["sig"]} {c["ch_eff"]}.{c["page"]}{c["col"]}{c["line"]}'))
                elif c["page"]:
                    ws = [w[0] for w in S.works_for_page(c["page"])]
                    if S.prefix_of(c["sig"] or "") not in ws:
                        rows.append((src, "RANGE", e["lemma"], f'{c["sig"]}{c["ch_eff"] or ""}.{c["page"]}{c["col"]}{c["line"]}'))
with open(ROOT / "data" / "audit.tsv", "w", encoding="utf-8") as f:
    for r in rows:
        f.write("\t".join(map(str, r)) + "\n")
print(Counter(r[1] for r in rows))
