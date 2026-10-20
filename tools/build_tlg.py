#!/usr/bin/env python3
"""從本機 TLG-E (經 Diogenes) 匯出亞里斯多德全集，逐行標 Bekker 頁欄行，供 quotecheck.py 比對。

輸出 data/tlg/aristotle.tsv (work, page, col, line, text) 與 data/tlg/editions.tsv (各作品所用版本)。
data/tlg/ 在 .gitignore 中：TLG 資料受授權限制，不可 commit / 上傳。
只能在本機執行 (需 Diogenes 與 TLG-E)；會自己啟動 diogenes-server.pl。
用法: python3 build_tlg.py [作品編號 ...]   (不給則全部；已匯出的作品會略過，可中斷續跑)
"""
import html
import re
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = Path("/usr/local/diogenes/server")
OUT = ROOT / "data" / "tlg"

# TLG 0086 作品編號 → Bekker 起訖頁 (sigla.TLG 所收者；MM 022 依卷章引用，不收)
RANGES = {
    "001": (24, 100), "002": (402, 435), "004": (800, 804), "005": (268, 313), "006": (1, 15),
    "007": (791, 799), "008": (462, 464), "009": (1214, 1249), "010": (1094, 1181), "012": (715, 789),
    "013": (314, 338), "014": (486, 638), "015": (704, 714), "016": (458, 462), "017": (16, 24),
    "018": (467, 470), "019": (968, 972), "020": (464, 467), "021": (698, 704), "023": (847, 858),
    "024": (449, 453), "025": (980, 1093), "026": (338, 390), "027": (830, 847), "028": (391, 401),
    "029": (1343, 1353), "030": (639, 697), "031": (184, 267), "032": (805, 814), "034": (1447, 1462),
    "035": (1252, 1342), "036": (859, 967), "037": (470, 480), "038": (1354, 1420), "040": (164, 184),
    "041": (436, 449), "042": (453, 458), "043": (481, 486), "044": (100, 164), "045": (1249, 1251),
    "046": (973, 973), "047": (974, 980),
}


def ensure_server():
    """8888 埠沒有 Diogenes 時自行啟動 (沙箱中每個指令網路獨立，須在同一程序內啟動)。"""
    try:
        socket.create_connection(("127.0.0.1", 8888), 1).close()
        return None
    except OSError:
        pass
    p = subprocess.Popen(["perl", "diogenes-server.pl"], cwd=SERVER,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            socket.create_connection(("127.0.0.1", 8888), 1).close()
            return p
        except OSError:
            time.sleep(0.5)
    sys.exit("Diogenes server did not start")


def get(loc):
    for _ in range(3):
        try:
            s = socket.create_connection(("127.0.0.1", 8888), timeout=60)
            s.sendall(f"GET /Diogenes.cgi?JumpTo=tlg,0086,{loc} HTTP/1.1\r\n"
                      "Host: localhost:8888\r\nConnection: close\r\n\r\n".encode())
            buf = b""
            while d := s.recv(65536):
                buf += d
            s.close()
            return buf.decode("utf-8", "replace")
        except OSError:
            continue
    return ""


def strip(h):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))).replace("\xa0", " ").strip()


def same(a, b):
    """作品名比較：行號標記中的 beta code (`%7` = `+`) 與表頭寫法不同，只比字母。"""
    f = lambda x: re.sub(r"[^A-Za-z]", "", x.replace("%7", ""))
    return f(a) == f(b)


def parse(h, st):
    """Diogenes 頁面 → (版本, [(page, col, line, text)])。

    頁面可能跨到前後作品：表頭列的是頁面開頭那部作品，作品交界的行號標記帶作品名
    (如 `De Xenophane, … 974a.1`)。目標作品名 st["title"] 從「頁碼為起始頁的帶名標記」學得，
    只收屬於目標作品的行。
    """
    t = strip(h)
    m = re.search(r"\), (.*?) \(0086: \d+\)", t)
    if not m:
        return "", []
    title = m.group(1).strip()
    b = re.search(r"Bekker page (\d+) ?([ab]), line (\d+)", t)
    head = t[m.end():b.start()] if b else ""
    # 頁面開頭若是非 Bekker 體系的作品 (如 Protrepticus)，表頭沒有 Bekker 位置：等第一個 Bekker 標記
    page, col, line = (int(b.group(1)), b.group(2), int(b.group(3))) if b else (0, "a", 0)
    ed = re.search(r"Ed\. (.*)", head) if same(title, st["title"]) else None
    ours = same(title, st["title"]) if st["title"] else st["lo"] <= page <= st["hi"]
    rows = []
    for cls, inner in re.findall(r'<div class="(citation|text(?:-noindent)?)"[^>]*>(.*?)</div>', h, re.S):
        if cls == "citation":
            ct = strip(inner)
            c = re.search(r"(.*?)\s*(\d+)([ab])\.(\d+)$", ct)
            if not c:                            # 非 Bekker 體系的標記 (另一部作品)
                name = re.sub(r"\s*\S*\d\S*$", "", ct)
                if name and not same(name, st["title"]):
                    ours = False
                continue
            if c:
                if c.group(1):
                    if not st["title"] and int(c.group(2)) == st["lo"]:
                        st["title"] = c.group(1)
                    ours = same(c.group(1), st["title"])
                page, col, line = int(c.group(2)), c.group(3), int(c.group(4))
            continue
        if re.search(r"</?b>", inner):          # 篇名、卷名等標題行 (可能跨兩個 div)，不算正文；詩行用 <font>，要收
            continue
        txt = strip(inner)
        if txt and ours and rows and rows[-1][:3] == (page, col, line):
            rows[-1] = (page, col, line, rows[-1][3] + " " + txt)   # 行中換段：TLG 同一行號分兩段
        elif txt and ours:
            rows.append((page, col, line, txt))
        line += 1                               # 只有空白的行 (如詩句前的空行) 也佔一個行號
    return (ed.group(1).strip()[:120] if ed else ""), rows


def crawl(work):
    lo, hi = RANGES[work]
    got, edition, st = {}, "", {"title": "", "lo": lo, "hi": hi}
    page, col, line = lo, "a", 1
    misses = 0
    while page <= hi:
        ed, rows = parse(get(f"{work}:{page}{col}:{line}"), st)
        edition = edition or ed
        # 作品開頭的頁面會連帶印出前一部作品的結尾：只收本作品頁碼範圍內的行
        rows = [r for r in rows if lo <= r[0] <= hi]
        # 所求行不存在時 (如該欄只有 39 行卻求第 40 行)，Diogenes 會跳到別處同號的行：
        # 回傳內容必須涵蓋所求位置，否則視為本欄已結束
        # (作品第一筆不檢查：作品可能從欄中間開始)
        if got and rows and not (rows[0][:3] <= (page, col, line) <= rows[-1][:3]):
            rows = []
        new = [r for r in rows if (r[0], r[1], r[2]) not in got]
        for r in new:
            got[(r[0], r[1], r[2])] = r[3]
        if new:
            misses = 0
            page, col, line = new[-1][:3]       # 從本次最後一行的下一行繼續
            line += 1
        elif not got and line < 40:              # 作品可能從欄中間開始 (如 APr 24a10)：同欄往下試
            line += 5
        else:                                    # 本欄已到底 (或此頁欄不存在)：跳下一欄
            misses += 1
            if misses > 6:
                break
            page, col, line = (page, "b", 1) if col == "a" else (page + 1, "a", 1)
    return work, edition, sorted(got.items())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    tsv, eds = OUT / "aristotle.tsv", OUT / "editions.tsv"
    done = set()
    if eds.exists():
        done = {l.split("\t")[0] for l in eds.read_text(encoding="utf-8").splitlines()}
    todo = [w for w in (sys.argv[1:] or RANGES) if w not in done]
    srv = ensure_server()
    with ThreadPoolExecutor(6) as ex, tsv.open("a", encoding="utf-8") as ft, eds.open("a", encoding="utf-8") as fe:
        for work, edition, lines in ex.map(crawl, todo):
            for (p, c, l), t in lines:
                ft.write(f"{work}\t{p}\t{c}\t{l}\t{t}\n")
            fe.write(f"{work}\t{len(lines)}\t{edition}\n")
            ft.flush(), fe.flush()
            print(f"{work}: {len(lines)} lines  {edition[:60]}", flush=True)
    if srv:
        srv.kill()


if __name__ == "__main__":
    main()
