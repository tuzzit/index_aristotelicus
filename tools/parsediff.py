#!/usr/bin/env python3
"""比對兩版 md2struct 對同一份 src/ 的解析結果 (改解析器前後的回歸檢查)。

用 git 某個版本的 tools/ (預設 HEAD) 與目前工作目錄的 tools/ 各自解析目前的 src/，
逐詞條比較每則用例的出處，列出有變化的地方。src/ 的校對修改不影響結果。

用法:
  python3 tools/parsediff.py                 HEAD vs 工作目錄，全書
  python3 tools/parsediff.py HEAD~3 3-200    指定版本與頁碼
  python3 tools/parsediff.py -n 0            只看統計，不列明細 (預設最多列 200 處)
"""
import difflib
import json
import os
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 在子行程中執行：載入指定目錄的 md2struct，解析目前的 src/，輸出精簡的 JSON
DRIVER = r"""
import json, sys
from pathlib import Path
tools, src, spec = sys.argv[1:4]
sys.path.insert(0, tools)
import md2struct as M
M.SRC = Path(src)
out = []
for e in M.build(M.pages(spec)):
    if e["t"] != "entry":
        continue
    lines = []
    for n in e["body"]:
        if n["t"] == "sense":
            lines.append("§%s %s" % (n["num"], n.get("label") or ""))
        elif n["t"] == "sub":
            lines.append("— %s" % n["lemma"])
        else:
            for it in n["items"]:
                cs = []
                for c in it["cites"]:
                    s = "%s%s.%s%s%s" % (c["sig"] or "", c["ch_eff"] or "", c["page"] or "",
                                         c["col"] or "", c["line"] or "")
                    if c["to"]:
                        s += "-" + c["to"]
                    if c.get("guess"):
                        s += "?"
                    if c["quals"]:
                        s += "[" + " ".join(c["quals"]) + "]"
                    cs.append(s)
                lines.append("%s  |  %s" % (" ".join(cs) or "-", it["text"][:60]))
    out.append([e["src"], e["lemma"], lines])
json.dump(out, sys.stdout, ensure_ascii=False)
"""


def run(tools, spec, tmp):
    drv = Path(tmp) / "driver.py"
    drv.write_text(DRIVER, encoding="utf-8")
    r = subprocess.run([sys.executable, "-I", str(drv), str(tools), str(ROOT / "src"), spec],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        sys.exit(f"{tools} 解析失敗:\n{r.stderr}")
    return json.loads(r.stdout)


def keyed(entries):
    """(頁, lemma, 同頁同名序號) → 用例行"""
    seen, out = defaultdict(int), {}
    for src, lemma, lines in entries:
        k = (src, lemma, seen[src, lemma])
        seen[src, lemma] += 1
        out[k] = lines
    return out


def main():
    args = [a for a in sys.argv[1:]]
    limit = 200
    if "-n" in args:
        i = args.index("-n")
        limit = int(args[i + 1])
        del args[i:i + 2]
    ref = args[0] if args else "HEAD"
    spec = args[1] if len(args) > 1 else "3-878"
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
        arc = subprocess.run(["git", "-C", str(ROOT), "archive", ref, "tools"], capture_output=True)
        if arc.returncode:
            sys.exit(arc.stderr.decode())
        subprocess.run(["tar", "-x", "-C", tmp], input=arc.stdout, check=True)
        old = keyed(run(Path(tmp) / "tools", spec, tmp))
        new = keyed(run(ROOT / "tools", spec, tmp))

    gone = [k for k in old if k not in new]
    added = [k for k in new if k not in old]
    changed = [k for k in new if k in old and old[k] != new[k]]
    n_lines = 0
    shown = 0
    for k in sorted(changed):
        d = list(difflib.unified_diff(old[k], new[k], lineterm="", n=0))[2:]
        n_lines += sum(1 for x in d if x[:1] in "+-")
        if shown < limit:
            print(f"== page-{k[0]:03d} {k[1]}")
            for x in d:
                if not x.startswith("@@"):
                    print("  " + x)
            shown += 1
    for tag, ks in (("詞條消失", gone), ("詞條新增", added)):
        for k in ks[:limit]:
            print(f"{tag}: page-{k[0]:03d} {k[1]}")
    print(f"\n{ref} → 工作目錄 ({spec})：{len(changed)} 個詞條有變化 ({n_lines} 行)，"
          f"詞條消失 {len(gone)}、新增 {len(added)}")
    sys.exit(1 if changed or gone or added else 0)


if __name__ == "__main__":
    main()
