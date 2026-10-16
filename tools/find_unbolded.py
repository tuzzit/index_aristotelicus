#!/usr/bin/env python3
"""找出漏標粗體的詞條：段首是非粗體的希臘字，且該字的字母序落在前後兩個粗體詞條之間。

用法:
  python3 tools/find_unbolded.py            列出候選 → data/unbolded.tsv
  python3 tools/find_unbolded.py --apply    把 status=ok 的候選加上粗體 (會跳過已校頁)

判斷依據: 續段 (被誤拆的段落) 的首字是任意文字，很少剛好落在相鄰兩詞條之間；
真正漏標的詞條首字則必定在其間。邊界情況 (等於前後詞條、首字非詞形) 標為 check。
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from md2struct import sortkey  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
OUT = ROOT / "data" / "unbolded.tsv"
GREEK = r"[Ͱ-Ͽἀ-῿]"
BOLD = re.compile(r"^\*\*([^*]+?)\*\*")
# 人工判定為續段 (非詞條) 的候選：(頁, 首字)
IGNORE = {("page-386", "κεφαλὴν")}
CAND = re.compile(rf"^({GREEK}[\wͰ-Ͽἀ-῿]*)([.,]?)(?=\s|$)")


def proofread_pages():
    t = (ROOT / "PROOFREADING.md").read_text(encoding="utf-8")
    return set(re.findall(r"page-(\d{3})", t.split("<!-- done -->")[1].split("<!-- /done -->")[0]))


def paragraphs():
    """依全書順序產生 (page, 段序, 段落文字)"""
    for f in sorted(SRC.glob("page-*.md")):
        for i, p in enumerate(f.read_text(encoding="utf-8").split("\n\n")):
            if p.strip():
                yield f.stem, i, p


def collect():
    pars = list(paragraphs())
    keys = []                                   # 每段的粗體詞條 key (非詞條為 None)
    for _, _, p in pars:
        b = BOLD.match(p)
        keys.append(sortkey(b.group(1).split()[0]) if b else None)
    rows = []
    for n, (page, i, p) in enumerate(pars):
        m = CAND.match(p)
        if not m or p.startswith("…") or (page, m.group(1)) in IGNORE:
            continue
        k = sortkey(m.group(1))
        prev = next((keys[j] for j in range(n - 1, -1, -1) if keys[j]), "")
        nxt = next((keys[j] for j in range(n + 1, len(pars)) if keys[j]), "ω" * 9)
        if not k or not (prev <= k <= nxt):
            continue
        status = "ok" if prev < k < nxt and len(k) > 2 else "check"
        cp = len(os.path.commonprefix([k, prev]))
        if prev and cp >= max(4, len(prev) - 3):
            status = "check"                    # 前一詞條的變格形 (ἀρετῆς 接 ἀρετή)：多為續段
        if i == 0:
            status = "check"                    # 頁首段：也可能是上一頁的續段
        rows.append((page, i, status, m.group(1) + m.group(2), prev, nxt, p[:70].replace("\n", " ")))
    return rows


def apply(rows):
    done = proofread_pages()
    todo = {}
    for page, i, status, head, *_ in rows:
        if status == "ok" and page[5:] not in done:
            todo.setdefault(page, []).append(i)
    n = 0
    for page, idx in todo.items():
        f = SRC / f"{page}.md"
        pars = f.read_text(encoding="utf-8").split("\n\n")
        for i in idx:
            pars[i] = CAND.sub(lambda m: f"**{m.group(1)}{m.group(2)}**", pars[i], count=1)
            n += 1
        f.write_text("\n\n".join(pars), encoding="utf-8")
    print(f"bolded {n} lemmas on {len(todo)} pages")


if __name__ == "__main__":
    rows = collect()
    with OUT.open("w", encoding="utf-8") as fh:
        fh.write("page\tpar\tstatus\thead\tprev\tnext\tcontext\n")
        for r in rows:
            fh.write("\t".join(map(str, r)) + "\n")
    print(f"{len(rows)} candidates ({sum(r[2] == 'ok' for r in rows)} ok) → {OUT.relative_to(ROOT)}")
    if "--apply" in sys.argv:
        apply(rows)
