#!/usr/bin/env python3
"""逐一開啟 data/entries.json 中每個出處的 Diogenes 連結，檢查是否落在正確位置。

結果寫入 data/diogenes_check.json (url -> 狀態)，md2struct.py 會讀取並據以標示連結。
  ok     目標頁欄出現在頁面上，且行號差距 ≤ 6
  near   落在同一頁欄但較遠，或跳到下一欄 (作品/頁欄起點晚於所求行號)
  fail   Diogenes 回報錯誤、或頁面上找不到所求頁欄
需要本機 Diogenes 伺服器 (localhost:8888) 正在執行。
用法: python3 check_diogenes.py [執行緒數=6]   (已檢查者會略過，可中斷續跑)
"""
import html
import json
import re
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import sigla as S  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "diogenes_check.json"


def fetch(loc):
    # Diogenes 伺服器回傳兩行狀態列，curl/urllib 不接受，故直接用 socket
    s = socket.create_connection(("127.0.0.1", 8888), timeout=60)
    s.sendall(f"GET /Diogenes.cgi?JumpTo=tlg,0086,{loc} HTTP/1.1\r\n"
              "Host: localhost:8888\r\nConnection: close\r\n\r\n".encode())
    buf = b""
    while True:
        d = s.recv(65536)
        if not d:
            break
        buf += d
    s.close()
    h = buf.decode("utf-8", "replace")
    h = re.sub(r"(?s)<script.*?</script>|<style.*?</style>", "", h)
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h)))


def judge(loc, text):
    if re.search(r"\bERROR\b|Error:", text):
        return "fail", re.search(r"(?:ERROR|Error:)[^.!]*", text).group(0)[:80]
    parts = loc.split(":")
    if parts[0] == "022":                       # MM：book.chapter
        b, c = parts[1], parts[2]
        if re.search(rf"\b{b}\.{c}\.\d+\.\d+", text):
            return "ok", ""
        return "fail", "chapter not on page"
    pc, ln = parts[1], int(parts[2])
    marks = [(m.group(1), int(m.group(2))) for m in re.finditer(r"\b(\d+[ab])\.(\d+)\b", text)]
    same = [l for p, l in marks if p == pc]
    if any(abs(l - ln) <= 6 for l in same):
        return "ok", ""
    if same:
        return "near", f"nearest {pc}.{min(same, key=lambda l: abs(l - ln))}"
    page, col = int(pc[:-1]), pc[-1]
    nxt = f"{page}b" if col == "a" else f"{page + 1}a"
    if any(p == nxt for p, _ in marks):
        return "near", f"jumped to {nxt}"
    return "fail", "page not found" + (f" (shows {marks[0][0]}.{marks[0][1]}…)" if marks else "")


def main():
    data = json.loads((ROOT / "data" / "entries.json").read_text(encoding="utf-8"))
    locs = set()
    for e in data:
        for n in e["body"]:
            for it in n.get("items", []):
                for c in it["cites"]:
                    loc = S.diogenes_loc(c["work"], c["page"], c["col"], c["line"], c["sig"], c["ch_eff"])
                    if loc:
                        locs.add(loc)
    res = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    todo = sorted(l for l in locs if l not in res)       # 可中斷後續跑
    print(len(locs), "links,", len(todo), "to check", flush=True)

    def one(loc):
        st, why = judge(loc, fetch(loc))
        r = {"status": st, "why": why}
        if st == "fail" and not loc.startswith("022"):
            # 版本行號差異 (TLG 依 OCT 等版本分行)：往前找最近可用的行
            w, pc, ln = loc.split(":")
            for k in range(int(ln) - 1, max(0, int(ln) - 12), -1):
                alt = f"{w}:{pc}:{k}"
                if judge(alt, fetch(alt))[0] == "ok":
                    r.update(status="alt", alt=alt, why=why + f" → {alt}")
                    break
        return loc, r

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(int(sys.argv[1]) if len(sys.argv) > 1 else 6) as ex:
        for i, (loc, r) in enumerate(ex.map(one, todo), 1):
            res[loc] = r
            if r["status"] != "ok":
                print(f"{r['status']:5} {loc:22} {r['why']}", flush=True)
            if i % 2000 == 0:
                OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
                print(f"-- {i}/{len(todo)}", flush=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    print(Counter(v["status"] for v in res.values()), "of", len(res))


if __name__ == "__main__":
    main()
