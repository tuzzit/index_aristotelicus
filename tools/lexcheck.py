#!/usr/bin/env python3
"""用 Diogenes 附的 LSJ 詞形表 (greek-lemmata.txt) 檢查詞條的希臘拼字。

對每個不在詞形表中的詞條字，嘗試 υ→ου (19 世紀排版 ȣ 連字常被誤認為 υ)，
若唯一一種改法能得到已知詞形，就列為建議修正。輸出 data/lexcheck.tsv
"""
import json, re, sys, unicodedata, pickle
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEM = Path("/usr/local/diogenes/dependencies/data/greek-lemmata.txt")
CACHE = ROOT / "data" / "greek-forms.pkl"
BETA = dict(zip("abgdezhqiklmncoprstufxyw", "αβγδεζηθικλμνξοπρστυφχψω"))


def beta_plain(b):
    return "".join(BETA.get(c, "") for c in b.lower())


def forms():
    if CACHE.exists():
        return pickle.loads(CACHE.read_bytes())
    s = set()
    for line in LEM.open(encoding="utf-8", errors="replace"):
        cols = line.rstrip("\n").split("\t")
        s.add(beta_plain(cols[0]))
        for c in cols[2:]:
            s.add(beta_plain(c.split(" (", 1)[0]))
    s.discard("")
    CACHE.write_bytes(pickle.dumps(s))
    return s


def plain(w):
    s = "".join(c for c in unicodedata.normalize("NFD", w) if not unicodedata.combining(c)).lower()
    return re.sub(r"[^α-ω]", "", s.replace("ς", "σ"))


def suggest(w, F):
    p = plain(w)
    if not p or p in F:
        return None
    idx = [m.start() for m in re.finditer("υ", p) if m.start() == 0 or p[m.start() - 1] != "ο"]
    cands = []
    for i in idx:
        q = p[:i] + "ου" + p[i + 1:]
        if q in F:
            cands.append(i)
    return cands


def main():
    F = forms()
    d = json.loads((ROOT / "data" / "entries.json").read_text(encoding="utf-8"))
    rows, unknown = [], 0
    for e in d:
        words = [e["lemma"]] + [n["lemma"] for n in e["body"] if n["t"] == "sub"]
        for lem in words:
            for w in re.findall(r"[Ͱ-Ͽἀ-῿]+", lem):
                c = suggest(w, F)
                if c is None:
                    continue
                unknown += 1
                if c:
                    rows.append(("page-%03d" % e["src"], lem, w, "υ→ου"))
                else:
                    rows.append(("page-%03d" % e["src"], lem, w, "unknown"))
    with open(ROOT / "data" / "lexcheck.tsv", "w", encoding="utf-8") as f:
        for r in rows:
            f.write("\t".join(r) + "\n")
    from collections import Counter
    print(Counter(r[3] for r in rows), "of", sum(1 for _ in d), "entries")


if __name__ == "__main__":
    main()
