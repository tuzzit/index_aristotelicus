#!/usr/bin/env python3
"""src/ 主檔的格式檢查 → data/lint.tsv (頁:行、類型、片段)。只列候選，不改檔。

  BOLD     段落中 ** 數目為奇數 (粗體沒關)
  BRACKET  段落中【】不成對
  COMMENT  <!-- --> 不成對，或不是 <!-- Bz: … --> 格式
  MIXED    拉丁字母緊貼希臘字母 (OCR 混用字形，如 ἔντερoν 的 o、AΖι 的 Ζ、1035ᵇ18Bz 漏空格)
  GRCAP    文獻縮寫用了希臘大寫 (cf Κ 571 → K)
  GLOSS    glosses.tsv 與詞條不同步：NOGLOSS 詞條無中譯、ORPHAN 中譯對不到詞條、DUP 重複
另見 data/diagnostics.tsv 的 "alphabetical order" (md2struct.py 產生)。

用法: python3 tools/lint_src.py [頁碼範圍，預設 3-878]   (GLOSS 只在全書時檢查)
"""
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import md2struct as M  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
OUT = ROOT / "data" / "lint.tsv"

# 希臘字母 (不含 ᾽ ᾿ ῾ ΄ 等獨立氣息/重音/省略符號)
GK = r"Ͱ-ͳͶ-ͽͿΆΈ-Ͽἀ-ᾼιῂ-ῌῐ-Ίῠ-Ῥῲ-ῼ"
# Bonitz 體例中合法的拉丁＋希臘連寫
MIXED_OK = re.compile(rf"(?:\bKa|\bA)Z(?=[{GK}])|(?<=\d)(?:n|sqq?|B)(?=[.,;)]|$)")
MIXED = re.compile(rf"[A-Za-z][{GK}]|[{GK}][A-Za-z]")
GRCAP = re.compile(r"(?:\bcf|[(;,])\s+([Α-Ω])\s+\d")


def scan_page(n, rows):
    name = f"page-{n:03d}"
    text = (SRC / f"{name}.md").read_text(encoding="utf-8")
    if text.count("<!--") != text.count("-->"):
        rows.append((name, "COMMENT", "<!-- 與 --> 數目不同"))
    for c in re.finditer(r"<!--(.*?)-->", text, flags=re.S):
        if not re.match(r" Bz: ", c.group(1)):
            rows.append((f"{name}:{text.count(chr(10), 0, c.start()) + 1}", "COMMENT", c.group(0)[:60]))
    body = re.sub(r"<!--.*?-->", lambda m: " " * len(m.group(0)), text, flags=re.S)
    pos = 0
    for par in re.split(r"(\n\s*\n)", body):
        line = body.count("\n", 0, pos) + 1
        pos += len(par)
        if par.count("**") % 2:
            rows.append((f"{name}:{line}", "BOLD", par.strip()[:60]))
        if par.count("【") != par.count("】"):
            rows.append((f"{name}:{line}", "BRACKET", par.strip()[:60]))
    for ln, l in enumerate(body.splitlines(), 1):
        for w in l.split():
            w = w.replace("**", "").strip("*")
            if MIXED.search(MIXED_OK.sub(" ", w)):
                rows.append((f"{name}:{ln}", "MIXED", w))
        for m in GRCAP.finditer(l):
            if re.search(r"\bHom\b[^()]{0,15}$", l[:m.start(1)]):
                continue                          # Hom Ε 661 = 伊利亞特卷號
            rows.append((f"{name}:{ln}", "GRCAP", l[max(0, m.start() - 20):m.end() + 10]))


def check_glosses(nums, rows):
    lemmas = Counter(unicodedata.normalize("NFC", e["lemma"]) for e in M.build(nums) if e["t"] == "entry")
    keys, orphans = Counter(), []
    for k, line in enumerate((SRC / "glosses.tsv").read_text(encoding="utf-8").splitlines(), 1):
        if "\t" in line and not line.startswith("#"):
            key = unicodedata.normalize("NFC", line.split("\t", 1)[0].strip())
            keys[key] += 1
            if key not in lemmas:
                orphans.append((k, key))
            elif keys[key] == 2:
                rows.append((f"glosses.tsv:{k}", "GLOSS", "DUP " + key))
    nogloss = [lem for lem in lemmas if lem not in keys]
    for k, key in orphans:
        # 詞條拼字改過而 glosses.tsv 沒跟著改：同字母序 (只差附加符號)，或中譯鍵多了後續文字
        cand = [lem for lem in nogloss if M.sortkey(lem) == M.sortkey(key) or key.startswith(lem + " ")]
        rows.append((f"glosses.tsv:{k}", "GLOSS", "ORPHAN " + key + (" → " + " / ".join(cand) if cand else "")))
    for lem in nogloss:
        rows.append(("", "GLOSS", "NOGLOSS " + lem))


def main():
    spec = sys.argv[1] if len(sys.argv) > 1 else "3-878"
    nums = M.pages(spec)
    rows = []
    for n in nums:
        if (SRC / f"page-{n:03d}.md").exists():
            scan_page(n, rows)
    if spec == "3-878":
        check_glosses(nums, rows)
    OUT.write_text("".join("\t".join(r) + "\n" for r in rows), encoding="utf-8")
    print(dict(Counter(r[1] for r in rows)), "→", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
