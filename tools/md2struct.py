#!/usr/bin/env python3
"""校對底稿 (src/page-NNN.md) -> 結構化資料 (data/entries.json) + LaTeX (struct/*.tex)

結構模型 (每個詞條)
  entry = {id, lemma, pages, xref?, body:[node...]}
  node  = {"t":"sense", num, label, title}      分項標題 (1. notio …)
        | {"t":"sub",   lemma}                   副詞條 (— **ἀγαπητός.**)
        | {"t":"group", items:[item...]}         以 — 分隔的一組用例
  item  = {text, pre?, cites:[cite...]}           一則用例：引文/說明 + 出處
  cite  = {sig, inh, ch, page, col, line, to, quals[], note?, work}
          sig  = 解析後的完整縮寫 (如 Ηε)；inh = 承前省略的部分 (如 Η)
          work = 通行縮寫 (EN, Pol. …)

用法: python3 md2struct.py 3-12
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import sigla as S  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
_gl = ROOT / "src" / "glosses.tsv"          # 詞條中譯：lemma<TAB>中譯 (可自行修改)
GLOSS = {}
if _gl.exists():
    for _line in _gl.read_text(encoding="utf-8").splitlines():
        if "\t" in _line and not _line.startswith("#"):
            _k, _v = _line.split("\t", 1)
            GLOSS[unicodedata.normalize("NFC", _k.strip())] = _v.strip()
_chk = ROOT / "data" / "diogenes_check.json"
CHECK = json.loads(_chk.read_text(encoding="utf-8")) if _chk.exists() else {}   # check_diogenes.py 的結果
OUT_TEX = ROOT / "struct"
OUT_JSON = ROOT / "data"

GR = "Ͱ-Ͽἀ-῿"
GRC = GR + "̀-ͯ"
SIGCH = "Α-Ωα-ωϛ"           # 縮寫只用無附加符號的希臘字母 (ϛ = 6，Probl. 卷號)

# ───────────────────────── 出處 (citation) 掃描 ─────────────────────────

RNG = r"(?:-(?:\d+[ᵃᵇ]|[ᵃᵇ])?\d+)?"
# A: [sig]ch.page col line   B: sig page col line   C: page col line   E: col line
ATOM_FULL = re.compile(
    rf"(?:(?P<sig>f|[{SIGCH}]{{1,4}})(?P<ch>\d+B?(?:-\d+)?)?|(?P<ch2>\d+B?(?:-\d+)?))\.(?P<pg>\d+)(?P<col>[ᵃᵇ])(?P<ln>\d+)(?P<rng>{RNG})")
ATOM_SIGPG = re.compile(rf"(?P<sig>f|[{SIGCH}]{{1,4}})(?P<pg>\d+)\s?(?P<col>[ᵃᵇ])(?P<ln>\d+)(?P<rng>{RNG})")
ATOM_PG = re.compile(rf"(?P<pg>\d+)(?P<col>[ᵃᵇ])(?P<ln>\d+)(?P<rng>{RNG})")
ATOM_COL = re.compile(rf"(?P<col>[ᵃᵇ])(?P<ln>\d+)(?P<rng>{RNG})")
# D: 只有書名與章 (Ρα6, Αβ11-14, f343-431)
ATOM_CH = re.compile(rf"(?P<sig>f|[{SIGCH}]{{1,4}})(?P<ch>\d+B?(?:-\d+)?)(?=[.,;:)\s]|$)(?!\.\d)")
LINE = re.compile(r"(?P<ln>\d+(?:-\d+)?)(?=[.,;)\s]|$)(?![ᵃᵇ.]\d)")
QUAL = re.compile(r"(?:Bz|Wz|Fr|Bk[¹²³]?|Spgl|Sus|Sylb|al|sqq?|Vhl(?: ad h l)?)(?=[.,;)\s]|$)")
SEP = re.compile(r"[.,;]?\s*")
NOT_AFTER = re.compile(r"(?:Hom|Hes|Emped|fr|Pind|Ol|Eur|Soph|Ant|p|n|v|l)\s*\(?\s*$")
SINGLE_OK = set("εκθφρξυζνχσ")      # 可單獨成為書名的單一字母
CONFUSABLE = {("Π", "Ρ"), ("Ρ", "Π"), ("Η", "Π"), ("Π", "Η"), ("Φ", "Γ"), ("Γ", "Φ")}   # OCR 常互誤的大寫


class Resolver:
    """依 Bonitz 的承前省略體例補全出處：ε7 承 Ηα1 → Ηε7；5.1097 → 同書同卷。"""

    def __init__(self):
        self.sig = self.ch = self.page = self.col = None

    def work_prefix(self, sig, page):
        cands = S.works_for_page(page) if page else []
        p = S.prefix_of(sig) if sig else None
        if cands:
            if p and any(w[0] == p for w in cands):
                return p, sig
            if sig and sig[0].isupper() and p:
                return p, sig                 # 大寫開頭必為完整書名縮寫 (頁碼可能是原書誤植)
            last = S.prefix_of(self.sig or "")
            w = next((c for c in cands if c[0] == last), cands[0])
            if sig:                       # sig 只是卷號
                return w[0], w[0] + sig
            if self.sig and S.prefix_of(self.sig) == w[0]:
                return w[0], self.sig
            return w[0], w[0]
        if p:
            return p, sig
        if sig and self.sig:              # 無頁碼的卷號
            q = S.prefix_of(self.sig)
            return q, (q or "") + sig
        return None, sig or self.sig

    def make(self, kind, m):
        g = m.groupdict()
        sig = g.get("sig")
        ch = g.get("ch") or g.get("ch2")
        pg = int(g["pg"]) if g.get("pg") else None
        col = g.get("col")
        ln = g.get("ln")
        if kind == "E":            # ᵇ10
            pg, ch, sig0 = self.page, self.ch, self.sig
        elif kind == "C":          # 1363ᵃ9
            ch, sig0 = self.ch, self.sig
        elif kind == "L":          # , 20
            pg, col, ch, sig0 = self.page, self.col, self.ch, self.sig
        else:
            sig0 = None
        if kind in ("A", "B", "D"):
            prefix, full = self.work_prefix(sig, pg if kind != "D" else None)
            if kind == "A" and not sig:
                full = self.sig if self.sig and S.prefix_of(self.sig) == prefix else full
        else:
            full = sig0
            prefix = S.prefix_of(full or "")
        guess = False
        if pg and full:
            cands = S.works_for_page(pg)
            pf = S.prefix_of(full)
            if cands and pf not in [w[0] for w in cands]:
                c0 = cands[0][0]
                rest = full[len(pf):] if pf else ""
                capital = bool(sig and sig[0].isupper() and kind in ("A", "B"))
                if c0 == "Μ" and full == "Α":
                    full, prefix, guess = "ΜΑ", c0, True          # 形上學 Α 卷單寫 Α
                elif pf and (pf[0].lower() == c0[0].lower() or (pf[0], c0[0]) in CONFUSABLE):
                    # 同字首 (Ζμ→Ζγ；Ζμ+HA ι 卷頁碼→Ζιι) 或形近 (Π↔Ρ)：改書名、保留卷號
                    if c0 == "Ζι" and not rest:
                        rest = "ι" if pg >= 608 else ""
                    full = c0 + rest
                    prefix, guess = c0, True
                elif not capital:
                    full = c0
                    prefix, guess = c0, True
                # 其餘 (大寫縮寫與頁碼完全不合) 保留原樣，由 audit 列為 RANGE
        given = sig or ""
        inh = full[: len(full) - len(given)] if full and given and full.endswith(given) else (
            full if not given else "")
        w = S.BY_PREFIX.get(S.prefix_of(full or "") or prefix)
        wname = S.work_name(full) if full else None
        cite = {"sig": full, "inh": inh, "ch": ch if kind in ("A", "D") else None,
                "ch_eff": ch, "page": pg, "col": {"ᵃ": "a", "ᵇ": "b"}.get(col, col),
                "line": ln, "to": (g.get("rng") or "").lstrip("-").replace("ᵃ", "a").replace("ᵇ", "b") or None,
                "quals": [], "work": wname or (w[2] if w else None), "kind": kind}
        if guess:
            cite["guess"] = True                     # 依 Bekker 頁碼推定書名 (原文縮寫與頁碼不合)
        self.sig, self.ch = full, ch
        if pg:
            self.page = pg
        if col:
            self.col = col
        return cite


def match_atom(s, i, in_run):
    """在位置 i 嘗試比對一個出處單元，回傳 (kind, match) 或 None"""
    if i > 0 and (s[i - 1].isalnum() or s[i - 1] in "ᵃᵇ"):
        return None
    for kind, rx in (("A", ATOM_FULL), ("B", ATOM_SIGPG)):
        m = rx.match(s, i)
        if m and (kind != "B" or m.group("sig")):
            if kind == "B" and NOT_AFTER.search(s[:i]):
                return None
            return kind, m
    m = ATOM_CH.match(s, i)
    if m and not NOT_AFTER.search(s[:i]):
        sig = m.group("sig")
        ok = sig == "f" or (len(sig) >= 2 and S.prefix_of(sig)) or (len(sig) == 1 and sig in SINGLE_OK)
        if in_run or ok:
            if ok:
                return "D", m
    if in_run:
        for kind, rx in (("C", ATOM_PG), ("E", ATOM_COL)):
            m = rx.match(s, i)
            if m:
                return kind, m
    return None


def balanced(s, i):
    """s[i] == '(' → 回傳對應 ')' 之後的位置"""
    d = 0
    for j in range(i, len(s)):
        d += {"(": 1, ")": -1}.get(s[j], 0)
        if d == 0:
            return j + 1
    return len(s)


UNSURE_CIT = re.compile(rf"【((?:f|[{SIGCH}]{{1,4}})?[\d.ᵃᵇ, -]*)】")


def scan(text, R):
    """把一組文字切成 [(item_text, [cites]) ...]"""
    items, buf, i, depth = [], [], 0, 0
    s = UNSURE_CIT.sub(r"\1", text)      # 出處上的【】不確定標記：去掉以便解析 (已列入 audit)
    while i < len(s):
        ch = s[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        hit = match_atom(s, i, False) if depth == 0 else None
        if not hit and depth == 0 and R.sig and i > 0 and s[i - 1] == " ":
            m0 = ATOM_PG.match(s, i)          # 說明文字後的 575ᵇ15 (承前書名)
            if m0 and (m0.end() == len(s) or s[m0.end()] in ".,;) ") \
                    and not re.search(r"(?:\bp|Schol|\bad)\s*$", s[:i]) \
                    and S.prefix_of(R.sig) in [w[0] for w in S.works_for_page(int(m0.group("pg")))]:
                hit = ("C", m0)
        if not hit:
            buf.append(ch)
            i += 1
            continue
        # ── 出處串 ──
        cites = []
        kind, m = hit
        cites.append(R.make(kind, m))
        j = m.end()
        while True:
            k = SEP.match(s, j).end()
            sep = s[j:k]
            nxt = match_atom(s, k, True) if k < len(s) else None
            cfm = re.match(r"(cf|coll|Bz ad|Wz ad)\s+", s[k:]) if not nxt else None
            if cfm:                       # 出處串中的 "cf ᵃ17" → 帶標記的出處
                nxt = match_atom(s, k + cfm.end(), True)
                if nxt:
                    c = R.make(*nxt)
                    c["pre"] = cfm.group(1)
                    cites.append(c)
                    j = nxt[1].end()
                    continue
            if nxt and "," in sep and nxt[0] == "A" and not nxt[1].group("sig") \
                    and nxt[1].group("ch2") and "-" not in nxt[1].group("ch2"):
                # Bonitz 體例：逗號後不換章 → "13, 36.1082ᵇ27" = 第 36 行；1082ᵇ27
                m2 = nxt[1]
                cites.append(R.make("L", re.match(r"(?P<ln>\d+)", m2.group("ch2"))))
                cm = ATOM_PG.match(s, m2.start("pg"))
                cites.append(R.make("C", cm))
                j = cm.end()
                continue
            if nxt and nxt[0] == "C" and cites[-1]["kind"] == "D" and sep.strip() in ("", "."):
                # "Ζμ15. 616ᵇ10"：章與頁被拆開 → 合成一筆
                d = cites.pop()
                R.sig, R.ch = d["sig"], d["ch_eff"]
                c = R.make("C", nxt[1])
                c["kind"], c["ch"] = "A", d["ch_eff"]
                c["inh"] = ""
                cites.append(c)
                j = nxt[1].end()
                continue
            if nxt:
                cites.append(R.make(*nxt))
                j = nxt[1].end()
                continue
            if "," in sep:
                lm = LINE.match(s, k)
                if lm:
                    cites.append(R.make("L", lm))
                    j = lm.end()
                    continue
            qm = QUAL.match(s, k) if sep.strip() in ("", ".") or sep == " " else None
            if qm and sep.strip() == "":
                cites[-1]["quals"].append(qm.group(0))
                j = qm.end()
                continue
            if s.startswith("(", k) and sep.strip() == "":
                e = balanced(s, k)
                cites[-1]["note"] = s[k + 1:e - 1]
                j = e
                continue
            break
        # 吃掉出處串後的句點
        k = SEP.match(s, j).end()
        rest = s[j:k]
        j = j + (1 if rest.startswith((".", ",", ";")) else 0)
        items.append(("".join(buf).strip(), cites))
        buf = []
        i = j
    tail = "".join(buf).strip()
    if tail:
        items.append((tail, []))
    return items


def split_xref(t, cites):
    """'cf φύσις 2 c. ἀεὶ τὸ χεῖρον …' → 交叉參照與下一則用例分開"""
    m = re.match(r"^((?:cf|v)\s+[^.()]{1,40}?)\.\s+(\S.*)$", t)
    if m:
        return [(m.group(1), []), (m.group(2), cites)]
    return [(t, cites)]


def to_items(text, R):
    out = []
    for t, cites in (x for pair in scan(text, R) for x in split_xref(*pair)):
        pre = None
        mm = re.search(r"(?:^|\s)(sim|cf|al)$", t)
        if mm and cites:
            pre = mm.group(1)
            t = t[:mm.start()].strip()
        t = t.rstrip(" ,;")
        if t.endswith(".") and not re.search(rf"(?:\b(?:sc|al|v|cf|i e|i q)|(?<![{GRC}])[{GR}])\.$", t):
            t = t[:-1].rstrip()
        out.append({"text": t, "pre": pre, "cites": cites})
    return out


# ───────────────────────── 詞條切分 ─────────────────────────

BOLD = re.compile(r"\*\*(.+?)\*\*")
SENSE_MID = re.compile(r"^(?P<num>\d)\.\s+(?:\*(?P<lab>[^*]+?)\.?\*\.?\s*)?")
SENSE_PAR = re.compile(r"^(?P<pre>[^\d*>]*?)\s*(?P<num>\d)\.\s+(?:\*(?P<lab>[^*]+?)\.?\*\.?\s*)?")


def strip_punct(w):
    return re.sub(r"[.,;:]+$", "", w).strip()


def sortkey(w):
    """字母序比較用：去附加符號、小寫、ς→σ，只留希臘字母；非希臘詞回傳 None"""
    s = "".join(c for c in unicodedata.normalize("NFD", w) if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^α-ω]", "", s.replace("ς", "σ"))
    return s or None


def headkey(p):
    b = BOLD.match(p)
    return sortkey(b.group(1)) if b else None


def join_cont(prev, cont):
    if prev.endswith("-") and re.match(r"[^\W\d]", cont):          # 跨頁斷字
        return prev[:-1] + cont
    return prev + ("" if re.search(r"\d$", prev) and cont[:1] in "ᵃᵇ" else " ") + cont


DIAG = []      # 給校對者的疑點清單
# 粗體但不是詞條：數字/字母分項標號、出處、單一書名縮寫
FALSE_HEAD = re.compile(rf"^\*\*\s*(?:[ᵃᵇ]\d|\d+[ᵃᵇ]|[ab]\d+|[A-Za-z]\.?\*\*|\d+\.|[a-h]\.\s|[a-h]\.\*\*|[A-H]\.\*\*|[IVX]+\.\*\*|[{SIGCH}]{{1,4}}\d|ΜΑ\b|MA\*\*|Π[αβγδεζηθ]\b|b\b|\d+\b|τί ἐστιν|ἄνθρωπος ἵππος|τὰ ζῷα τὰ)")


def load_paragraphs(nums):
    """回傳 [[text, firstpage, lastpage, srcpage]]；處理跨頁續接。

    - 頁首非粗體段 (或以 … 開頭) → 接到上一段
    - 頁首粗體段若不合字母序 (落在上一頁末詞條與本頁下一詞條之間以外) → 視為續接
    - 頁中非粗體段 → 同一詞條下的新段落 (> )
    """
    pars = []
    last_key = None
    for n in nums:
        page = n - 2
        txt = (SRC / f"page-{n:03d}.md").read_text(encoding="utf-8")
        txt = re.sub(r"\s*<!--.*?-->", "", txt, flags=re.S)   # 校對註解 (如 <!-- Bz: … -->) 不進排版
        ps = [p.strip().replace("\n", " ") for p in re.split(r"\n\s*\n", txt) if p.strip()]
        for k, p in enumerate(ps):
            if p.startswith("# "):
                pars.append([p, page, page, n])
                continue
            first = k == 0 or (k == 1 and ps[0].startswith("# ") and not ps[0].upper().startswith("# ADDENDA"))
            cont = p.startswith("…")
            if first and not cont and p.startswith("**") and pars:
                hk = headkey(p)
                nxt = next((headkey(q) for q in ps[k + 1:] if headkey(q)), None)
                if hk and last_key and (hk == last_key or (nxt and last_key <= nxt and not (last_key <= hk <= nxt))):
                    DIAG.append((n, "page-start bold treated as continuation", p[:60]))
                    p = BOLD.sub(lambda m: m.group(1), p, count=1)
                    cont = True
            if first and not p.startswith("**") and not p.startswith(">") and pars:
                cont = True
            if cont and pars:
                c = p.lstrip("… ").strip()
                pars[-1][0] = join_cont(pars[-1][0], c)
                pars[-1][2] = page
                continue
            if p.startswith("**") and "**" not in p[2:]:
                p = p[2:]                         # 粗體只開不關 (OCR)
            if p.startswith("**") and pars and FALSE_HEAD.match(p):
                # **13.** / **a. ἡ σὰρξ τί ἐστιν** / **Ζιγ7.** 等分項標記被誤標為詞條
                DIAG.append((n, "bold sub-label → paragraph", p[:50]))
                p = BOLD.sub(lambda m: m.group(1), p, count=1)
            if not p.startswith(("**", ">")) and pars:
                p = "> " + p
            pars.append([p.lstrip("… ").strip(), page, page, n])
            hk = headkey(p)
            if hk:
                last_key = hk
    return pars


def split_groups(body):
    return [g.strip() for g in re.split(r"\s+—\s+|^—\s+", body) if g.strip()]


def parse_body(body, R, nodes, first=False):
    for gi, g in enumerate(split_groups(body)):
        m = SENSE_MID.match(g)
        if m:
            nodes.append({"t": "sense", "num": m.group("num"), "label": m.group("lab"), "title": None})
            g = g[m.end():]
        b = BOLD.match(g)
        if b and not (first and gi == 0):
            nodes.append({"t": "sub", "lemma": strip_punct(b.group(1))})
            g = g[b.end():].lstrip(" ,.")
        if g:
            nodes.append({"t": "group", "items": to_items(g, R)})


ADDREF = re.compile(r"^\s*,?\s*p\s?(?P<pg>\d+)\s?(?P<col>[ᵃᵇ])\s?(?P<ln>\d+)\s*(?P<a>a:|adde:?)?\s*")


def build(nums):
    entries, cur, letter, addenda = [], None, None, False
    prevkey = None
    for text, p0, p1, src in load_paragraphs(nums):
        if text.startswith("# "):
            if "ADDENDA" in text.upper():
                addenda = True
                entries.append({"t": "addenda"})
            continue
        if text.startswith(">") and cur:
            t = text.lstrip("> ").strip()
            m = SENSE_PAR.match(t)
            if m and (m.group("lab") or not m.group("pre")):
                cur["body"].append({"t": "sense", "num": m.group("num"), "label": m.group("lab"),
                                    "title": m.group("pre").strip() or None})
                t = t[m.end():]
            parse_body(t, cur["R"], cur["body"])
            cur["pages"][1] = p1
            continue
        b = BOLD.match(text)
        lemma = strip_punct(b.group(1)) if b else text.split()[0]
        rest = text[b.end():] if b else text[len(lemma):]
        sm = re.search(rf"\s+((?:f|[{SIGCH}]{{1,4}}))$", lemma)
        if sm and re.match(r"\s*\d", rest) and len(lemma.split()) >= 2 and (
                S.prefix_of(sm.group(1)) or sm.group(1) == "f"):
            # 粗體多涵蓋了出處的書名縮寫 (**Ἐργόφιλος Ρβ** 9.1380ᵇ12)
            rest = sm.group(1) + rest.lstrip()
            lemma = lemma[:sm.start()]
        key = sortkey(lemma)
        if not addenda and key:
            lt = key[0]
            if lt != letter and (letter is None or lt > letter):
                letter = lt
                entries.append({"t": "letter", "letter": lt.upper()})
            if prevkey and key < prevkey and not prevkey.startswith(key[:3]):
                DIAG.append((src, "alphabetical order", f"{lemma}  after  {entries[-1].get('lemma', '?') if entries else ''}"))
            prevkey = key
        cur = {"t": "entry", "lemma": lemma, "pages": [p0, p1], "body": [], "R": Resolver(), "src": src}
        if addenda:
            cur["addenda"] = True
            am = ADDREF.match(rest)
            if am:
                cur["ref"] = {"page": int(am.group("pg")), "col": {"ᵃ": "a", "ᵇ": "b"}[am.group("col")],
                              "line": am.group("ln")}
                rest = rest[am.end():]
        xm = re.match(r"^\s*v\.?\s+([^\s.]+)\.?\s*$", rest)
        if xm:
            cur["xref"] = xm.group(1)
        else:
            parse_body(rest.lstrip(" ,.").strip(), cur["R"], cur["body"], first=True)
        entries.append(cur)
    for i, e in enumerate(x for x in entries if x["t"] == "entry"):
        e["id"] = f"e{i + 1:05d}"
        e.pop("R", None)
    return entries


# ───────────────────────── LaTeX 輸出 ─────────────────────────

def norm(w):
    return unicodedata.normalize("NFC", w)


def plain(w):
    return "".join(c for c in unicodedata.normalize("NFD", w) if not unicodedata.combining(c)).lower()


def _cjk_cmap():
    try:
        from fontTools.ttLib import TTFont
        f = "/usr/local/texlive/texmf-local/fonts/opentype/myfonts/rixingsong-1.0-semibold.otf"
        return set(TTFont(f).getBestCmap())
    except Exception:
        return set(range(0x110000))      # 找不到字型就不處理


CJK_CMAP = _cjk_cmap()


def esc(s):
    s = (s.replace("\\", r"\textbackslash{}").replace("&", r"\&").replace("%", r"\%")
          .replace("#", r"\#").replace("_", r"\_").replace("$", r"\$"))
    return (s.replace("ᵃ", r"\textsuperscript{a}").replace("ᵇ", r"\textsuperscript{b}")
             .replace("ᶜ", r"\textsuperscript{c}"))


TAGS = {"opp", "syn", "coni", "dist", "def", "cf", "ie", "iq", "sc", "sim", "v", "vel",
        "act", "pass", "absol", "veluti", "hv", "shv", "vshv", "vl", "al", "fort", "coll",
        "ci", "om", "resp", "descr", "etymol", "metaph", "proprie", "adv", "fut", "intr",
        "cinf", "cgen", "cdat", "cacc", "ad hl"}
MULTI = [("v s h v", "vshv"), ("s h v", "shv"), ("h v", "hv"), ("i e", "ie"), ("i q", "iq"),
         ("v l", "vl"), ("c inf", "cinf"), ("c gen", "cgen"), ("c dat", "cdat"), ("c acc", "cacc")]
TAGSHOW = {"ie": "i.e.", "iq": "i.q.", "hv": "h.v.", "shv": "s.h.v.", "vshv": "v.s.h.v.",
           "vl": "v.l.", "cinf": "c.inf.", "cgen": "c.gen.", "cdat": "c.dat.", "cacc": "c.acc."}
REL = {"opp", "syn", "coni", "dist", "def", "cf", "ie", "iq", "v"}


class TexWriter:
    def __init__(self, lemmas, mainid, pageid):
        self.lemmas = lemmas          # plain(lemma) -> id
        self.mainid = mainid          # 正文詞條 (補遺連回用)
        self.pageid = pageid          # Bonitz 頁碼 -> 該頁開始處所在詞條

    def gloss(self, lemma):
        # 主 CJK 字型 (日星宋體) 缺的字改用 myfonts 的 \rare{} (Noto Sans CJK TC)
        return "".join(r"\rare{%s}" % ch if "\u3400" <= ch <= "\U0002FFFF" and ord(ch) not in CJK_CMAP
                       else ch for ch in esc(GLOSS.get(norm(lemma), "")))

    def cite(self, c, showwork=False):
        sig = c["sig"] or ""
        inh = c["inh"] or ""
        given = sig[len(inh):]
        sigtex = (r"\ih{%s}" % inh if inh else "") + given
        if showwork and c["work"]:
            sigtex = r"\wk{%s}" % esc(c["work"]) + sigtex
        ch = c["ch_eff"] or ""
        chtex = ch if c["ch"] else (r"\ih{%s}" % ch if ch else "")
        pg = str(c["page"] or "")
        pgtex = pg if c["kind"] in ("A", "B", "C") else (r"\ih{%s}" % pg if pg else "")
        q = "".join(r"\cq{" + esc(x) + "}" for x in c["quals"])
        if c.get("pre"):
            sigtex = r"\cpre{%s}" % c["pre"] + sigtex
        note = r"\cnote{" + self.inline(c["note"], ctx=c) + "}" if c.get("note") else ""
        url = S.diogenes_url(c["work"], c["page"], c["col"], c["line"], c["sig"], c["ch_eff"])
        chk = CHECK.get(S.diogenes_loc(c["work"], c["page"], c["col"], c["line"], c["sig"], c["ch_eff"]))
        if chk:
            c["diogenes"] = chk["status"]
            if chk["status"] == "alt":
                url = S.DIOGENES.format(work=chk["alt"].split(":")[0], loc=chk["alt"].split(":", 1)[1])
            elif chk["status"] == "fail":
                url = ""
        return (r"\cit{%s}{%s}{%s}{%s}{%s}{%s}{%s}" % (
            sigtex, chtex, pgtex, c["col"] or "", c["line"] or "", c["to"] or "", url)) + \
            (r"\cguess" if c.get("guess") else "") + q + note

    def cites(self, cs, pre):
        if not cs:
            return ""
        p = r"\cpre{%s}" % pre if pre else ""
        out, prev = [], None
        for c in cs:
            out.append(self.cite(c, showwork=c["work"] != prev))
            prev = c["work"]
        return p + r"\citsep ".join(out)

    def inline(self, s, ctx=None):
        """行內文字：希臘文 / 拉丁說明 / 關係標記 / 行內出處"""
        if not s:
            return ""
        R = Resolver()
        if ctx:      # 括號附註中的 ᵃ39 承接所屬出處
            R.sig, R.ch, R.page = ctx["sig"], ctx["ch_eff"], ctx["page"]
            R.col = {"a": "ᵃ", "b": "ᵇ"}.get(ctx["col"])
        ph = []

        def keep(tex):
            ph.append(tex)
            return f"\x00{len(ph) - 1}\x01"

        # 行內出處 (括號中的)
        out, i = [], 0
        while i < len(s):
            hit = match_atom(s, i, ctx is not None)
            if hit:
                kind, m = hit
                c = R.make(kind, m)
                out.append(keep(self.cite(c)))
                i = m.end()
                # 後續同串
                while True:
                    k = SEP.match(s, i).end()
                    nxt = match_atom(s, k, True)
                    if nxt:
                        out.append(s[i:k])
                        out.append(keep(self.cite(R.make(*nxt))))
                        i = nxt[1].end()
                        continue
                    break
                continue
            out.append(s[i])
            i += 1
        s = "".join(out)
        # Bonitz 本書頁碼 (cf Ἀριστοτέλης p 96ᵇ3) → 連到該頁的詞條
        def bref(m):
            pg = int(m.group(1))
            tid = self.pageid.get(pg)
            lab = r"p.\,%d\textsuperscript{%s}%s" % (pg, {"ᵃ": "a", "ᵇ": "b"}[m.group(2)], m.group(3))
            return keep(r"\bref{%s}{%s}" % (tid, lab) if tid else r"\la{%s}" % lab)
        s = re.sub(r"(?<![\w])p ?(\d{1,3})\s?([ᵃᵇ])(\d+)", bref, s)
        s = re.sub(r"\*\*(.+?)\*\*", lambda m: keep(r"\form{" + self.greek(m.group(1)) + "}"), s)
        s = re.sub(r"\*(.+?)\*", lambda m: keep(r"\la{\emph{" + esc(m.group(1)) + "}}"), s)
        s = re.sub(r"【(.+?)】", lambda m: keep(r"\unsure{" + self.greek(m.group(1)) + "}"), s)
        for a, b in MULTI:
            s = re.sub(rf"(?<![A-Za-z]){a}(?![A-Za-z])", b, s)
        s = s.replace("'", "’")
        toks = re.findall(rf"\x00\d+\x01|[{GR}][{GRC}’]*|[A-Za-zÀ-ÿ²³¹]+|\s+|.", s)
        res, gbuf, lbuf = [], [], []

        def flush_g():
            if gbuf:
                txt = "".join(gbuf)
                tail = re.search(r"[\s,·.;:]*$", txt).group(0)
                res.append(r"\grc{" + esc(txt[:len(txt) - len(tail)]) + "}" + esc(tail))
                gbuf.clear()

        def flush_l():
            if lbuf:
                txt = "".join(lbuf)
                tail = re.search(r"\s*$", txt).group(0)
                res.append(r"\la{" + esc(txt[:len(txt) - len(tail)]) + "}" + tail)
                lbuf.clear()

        mode = None
        for t in toks:
            if t.startswith("\x00"):
                flush_g(); flush_l(); mode = None
                res.append(ph[int(t[1:-1])])
            elif re.match(rf"[{GR}]", t):
                flush_l(); mode = "g"; gbuf.append(t)
            elif re.match(r"[A-Za-zÀ-ÿ]", t):
                flush_g()
                if t in TAGS and t not in ("al",) or t in TAGSHOW:
                    flush_l(); mode = None
                    shown = TAGSHOW.get(t, t)
                    res.append((r"\rel{%s}" if t in REL else r"\mtag{%s}") % shown)
                else:
                    mode = "l"; lbuf.append(t)
            else:
                if mode == "g":
                    gbuf.append(t)
                elif mode == "l":
                    lbuf.append(t)
                else:
                    res.append(esc(t))
        flush_g(); flush_l()
        out = "".join(res)
        # 交叉參照：\rel{cf}/\rel{v} 之後的詞若是本冊詞條 → 超連結
        def link(m):
            word = m.group(2)
            tid = self.lemmas.get(plain(word))
            return m.group(1) + (r"\xref{%s}{%s}" % (tid, word) if tid else r"\grc{%s}" % word)
        out = re.sub(r"(\\rel\{(?:cf|v)\}\s*)\\grc\{([^ {}]+)\}", link, out)
        return out

    def greek(self, s):
        return self.inline(s)

    def item(self, it):
        txt = self.inline(it["text"]) if it["text"] else r"\lemtilde"
        return r"\attest{%s}{%s}" % (txt, self.cites(it["cites"], it["pre"]))

    def entry(self, e):
        L = []
        lem = e["lemma"]
        pages = f"{e['pages'][0]}" if e["pages"][0] == e["pages"][1] else f"{e['pages'][0]}–{e['pages'][1]}"
        if e.get("xref"):
            tid = self.lemmas.get(plain(e["xref"]))
            tgt = r"\xref{%s}{%s}" % (tid, e["xref"]) if tid else r"\grc{%s}" % e["xref"]
            return r"\xentry{%s}{%s}{%s}{%s}{%s}" % (e["id"], lem, pages, tgt, self.gloss(lem)) + "\n"
        if e.get("addenda"):
            r = e.get("ref")
            main = self.mainid.get(plain(lem))
            pages = r"Addenda" + (r" → p.\,%d\textsuperscript{%s}%s" % (r["page"], r["col"], r["line"]) if r else "")
            if main:
                pages = r"\hyperlink{%s}{%s}" % (main, pages)
        L.append(r"\begin{entry}{%s}{%s}{%s}{%s}" % (e["id"], lem, pages, self.gloss(lem)))
        open_group = False
        for n in e["body"]:
            if n["t"] == "sense":
                if open_group:
                    L.append(r"\end{usegroup}"); open_group = False
                L.append(r"\sense{%s}{%s}{%s}" % (n["num"], esc(n["label"] or ""),
                                                  self.inline(n["title"]) if n["title"] else ""))
            elif n["t"] == "sub":
                if open_group:
                    L.append(r"\end{usegroup}"); open_group = False
                L.append(r"\sublemma{%s}{%s}" % (n["lemma"], self.gloss(n["lemma"])))
            else:
                if open_group:
                    L.append(r"\end{usegroup}")
                L.append(r"\begin{usegroup}")
                open_group = True
                for it in n["items"]:
                    L.append(self.item(it))
        if open_group:
            L.append(r"\end{usegroup}")
        L.append(r"\end{entry}")
        return "\n".join(L) + "\n"


def write_tex(entries):
    OUT_TEX.mkdir(exist_ok=True)
    lemmas = {plain(e["lemma"]): e["id"] for e in reversed(entries) if e["t"] == "entry"}
    for e in entries:
        if e["t"] == "entry":
            for n in e["body"]:
                if n["t"] == "sub":
                    lemmas.setdefault(plain(n["lemma"]), e["id"])
    mainid = {plain(e["lemma"]): e["id"] for e in entries if e["t"] == "entry" and not e.get("addenda")}
    pageid = {}
    for e in entries:
        if e["t"] == "entry" and not e.get("addenda"):
            for pg in range(e["pages"][0], e["pages"][1] + 1):
                pageid.setdefault(pg, e["id"])
    W = TexWriter(lemmas, mainid, pageid)
    body = []
    for e in entries:
        if e["t"] == "letter":
            body.append(r"\lettersection{%s}" % e["letter"])
        elif e["t"] == "addenda":
            body.append(r"\addendasection")
        else:
            body.append(W.entry(e))
    (OUT_TEX / "entries.tex").write_text("\n".join(body), encoding="utf-8")
    # 詞條索引
    idx = [r"\idxitem{%s}{%s}{%s}" % (e["id"], e["lemma"], e["pages"][0])
           for e in entries if e["t"] == "entry" and not e.get("addenda")]
    (OUT_TEX / "lemmaindex.tex").write_text("\n".join(idx) + "\n", encoding="utf-8")
    # 縮寫表
    def zh(a):
        return "／".join(S.ZH.get(x.strip(), "") for x in a.split(","))
    rows = [r"{\sffamily\bfseries\color{citc}%s} & \grc{%s} & {\sffamily %s} & %s & {\sffamily\small %d--%d}\\"
            % (p, t, esc(a), zh(a), s, e) for p, t, a, s, e in S.WORKS]
    (OUT_TEX / "sigla.tex").write_text(
        "\\begin{longtable}{@{}l p{0.40\\linewidth} l p{0.24\\linewidth} l@{}}\n\\toprule\n"
        "{\\sffamily 縮寫} & {\\sffamily Bonitz 書名} & {\\sffamily 通行} & 中譯名 & {\\sffamily Bekker}\\\\\n"
        "\\midrule\n\\endhead\n" + "\n".join(rows) + "\n\\bottomrule\n\\end{longtable}\n", encoding="utf-8")


def pages(spec):
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += range(int(a), int(b or a) + 1)
    return out


def main():
    entries = build(pages(sys.argv[1]))
    write_tex(entries)          # 先產生 LaTeX (同時把連結檢查結果寫進各出處)
    OUT_JSON.mkdir(exist_ok=True)
    data = [e for e in entries if e["t"] == "entry"]
    for e in data:
        for n in e["body"]:
            for it in n.get("items", []):
                pass
    for e in data:
        g = GLOSS.get(norm(e["lemma"]))
        if g:
            e["zh"] = g
    (OUT_JSON / "entries.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(OUT_JSON / "diagnostics.tsv", "w", encoding="utf-8") as f:
        for d in DIAG:
            f.write("page-%03d\t%s\t%s\n" % d)
    print(len(DIAG), "diagnostics → data/diagnostics.tsv")
    n_items = sum(len(n["items"]) for e in data for n in e["body"] if n["t"] == "group")
    n_cites = sum(len(it["cites"]) for e in data for n in e["body"] if n["t"] == "group" for it in n["items"])
    print(f"{len(data)} entries, {n_items} items, {n_cites} citations")


if __name__ == "__main__":
    main()
