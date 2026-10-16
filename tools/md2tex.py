#!/usr/bin/env python3
"""校對底稿 (latex/src/page-NNN.md) -> LaTeX 內文 (latex/body/page-NNN.tex)

底稿標記約定
  # Α                 字母分節標題
  **lemma** ...       段首粗體 = 詞條 (懸掛縮排); 詞條字以疏排 (Sperrung) 排出
  > ...               詞條內的分項段落 (首行縮排), 例如 "> 2. *species* ..."
  … ...               頁首續接上一頁最後一段 (會與前段接成同一段)
  **x** (段中)        段中疏排的子詞條, 例如 — **ἀγαπητός.**
  *x*                 斜體 (notio, species 等拉丁小標)
  【x】                不確定的讀法, 以醒目方式排出供校對
  ᵃ ᵇ                 Bekker 欄位 (轉為 \ba \bb)

用法: python3 md2tex.py 3-12     (輸出 body/page-NNN.tex 與 body/pages.tex)
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
OUT = ROOT / "body"

GREEK = "\u0370-\u03ff\u1f00-\u1fff"
COMB = "\u0300-\u036f"
# 一個希臘詞 (允許省音符 ’ 結尾)
GWORD = rf"[{GREEK}][{GREEK}{COMB}]*’?"
# 以空白相連的希臘詞串
GRUN = re.compile(rf"{GWORD}(?:[ ,·]+{GWORD})*")

PUNCT_TAIL = re.compile(r"([.,;:·]+)$")


def esc(s: str) -> str:
    return (s.replace("\\", r"\textbackslash{}")
             .replace("&", r"\&").replace("%", r"\%")
             .replace("#", r"\#").replace("_", r"\_"))


def greek(s: str) -> str:
    """把希臘文串包進 \\grc{} 以取得希臘文斷字。"""
    def rep(m):
        txt = m.group(0)
        tail = ""
        mm = re.search(r"[ ,·]+$", txt)
        if mm:
            txt, tail = txt[:mm.start()], mm.group(0)
        return r"\grc{" + txt + "}" + tail
    return GRUN.sub(rep, s)


def inline(s: str) -> str:
    s = esc(s)
    # 希臘文中的省音 ' -> ’
    s = re.sub(rf"(?<=[{GREEK}{COMB}])'", "’", s)
    s = s.replace("'", "’")
    s = s.replace("ᵃ", r"\ba{}").replace("ᵇ", r"\bb{}")
    # 移除 \ba{} 後接數字時多餘的 {}
    s = re.sub(r"\\b([ab])\{\}(?=\d)", r"\\b\1 ", s)
    s = re.sub(r"\\b([ab]) (\d)", r"\\b\1\2", s)

    def lem(m):
        body = m.group(1)
        tail = ""
        mm = PUNCT_TAIL.search(body)
        if mm:
            body, tail = body[:mm.start()], mm.group(1)
        return "\x00L" + body + "\x00E" + tail

    s = re.sub(r"\*\*(.+?)\*\*", lem, s)
    s = re.sub(r"\*(.+?)\*", lambda m: "\x00I" + m.group(1) + "\x00E", s)
    s = re.sub(r"【(.+?)】", lambda m: "\x00U" + m.group(1) + "\x00E", s)
    s = greek(s)
    s = (s.replace("\x00L", r"\lemma{").replace("\x00I", r"\emph{")
          .replace("\x00U", r"\unsure{").replace("\x00E", "}"))
    return s


def headword(par: str) -> str:
    m = re.match(r"\*\*(.+?)\*\*", par)
    if not m:
        return ""
    return PUNCT_TAIL.sub("", m.group(1)).strip()


def paragraphs(text: str):
    return [p.strip().replace("\n", " ") for p in re.split(r"\n\s*\n", text) if p.strip()]


PAGEMARK = re.compile(r"^⁅(\d+)⁆\s*")


def convert(pars):
    out = []
    for p in pars:
        if p.startswith("# "):
            out.append(r"\lettersection{" + p[2:].strip() + "}")
            continue
        sub = p.startswith(">")
        if sub:
            p = p.lstrip("> ").strip()
        orig = ""
        m = PAGEMARK.match(p)
        if m:
            orig = r"\origpage{" + m.group(1) + "}"
            p = p[m.end():]
        hw = headword(p)
        if sub:
            mark = r"\lemmamark{" + hw + "}" if hw else ""
            out.append(r"\subpar" + mark + orig + " " + inline(p))
        else:
            out.append(r"\entry{" + hw + "}" + orig + inline(p))
    # 段中的換頁標記 (續接段落)
    return [re.sub(r"⁅(\d+)⁆\s*", r"\\origpage{\1}", s) for s in out]


def pages(spec):
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += range(int(a), int(b or a) + 1)
    return out


def main():
    OUT.mkdir(exist_ok=True)
    nums = pages(sys.argv[1])
    carry = None          # 上一頁最後一段 (等待可能的續接)
    files = []
    for n in nums:
        pars = paragraphs((SRC / f"page-{n:03d}.md").read_text(encoding="utf-8"))
        mark = f"⁅{n - 2}⁆ "          # 原書頁碼 = 檔案頁碼 - 2
        if pars and pars[0].startswith("…"):
            cont = mark + pars.pop(0).lstrip("… ").strip()
            if carry is None:
                pars.insert(0, "> " + cont)
            else:
                carry[-1] = carry[-1] + " " + cont
        else:
            i = next((k for k, q in enumerate(pars) if not q.startswith("# ")), None)
            if i is not None:
                q = pars[i]
                pars[i] = ("> " + mark + q.lstrip("> ")) if q.startswith(">") else mark + q
        if carry is not None:
            files[-1][1].extend(carry)
        carry = pars[-1:]
        files.append((n, pars[:-1]))
    if carry:
        files[-1][1].extend(carry)

    for n, pars in files:
        body = "\n\n".join(convert(pars))
        (OUT / f"page-{n:03d}.tex").write_text(
            f"% ---- 原書 p. {n - 2} (page-{n:03d}) ----\n" + body + "\n",
            encoding="utf-8")
    (OUT / "pages.tex").write_text(
        "".join(f"\\input{{body/page-{n:03d}}}\n" for n, _ in files), encoding="utf-8")
    print("converted", len(files), "pages")


if __name__ == "__main__":
    main()
