#!/usr/bin/env python3
"""OCR markdown (pages_out/) -> 校對底稿 (latex/src/) 的機械正規化。

用法: python3 normalize.py 4-12        (不會覆蓋 src/ 中已存在的檔案, 加 -f 強制)
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import sigla as S  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OCR = ROOT / "pages_out"
SRC = ROOT / "latex" / "src"


import json  # noqa: E402
_fx = Path(__file__).resolve().parents[1] / "src" / "ocr_fixes.json"
# 人工校正表 {"page-NNN": [[誤, 正], ...]}：在正規化之後套用，重跑 normalize 不會遺失
FIXES = json.loads(_fx.read_text(encoding="utf-8")) if _fx.exists() else {}

FULLWIDTH = str.maketrans("ＡＢＥＺＨＩＫＭＮＯＰＴＸＹ", "ΑΒΕΖΗΙΚΜΝΟΡΤΧΥ")
LAT2GRK = str.maketrans("ABEZHIKMNOPTXY", "ΑΒΕΖΗΙΚΜΝΟΡΤΧΥ")


def greek_sigla(t: str) -> str:
    """書名縮寫中誤用的拉丁大寫 (Zμγ, Pβ, Mδ, K11.) -> 希臘大寫"""
    t = re.sub(r"(?<![A-Za-z])([ABEZHIKMNOPTXY])(?=[α-ω])",
               lambda m: m.group(1).translate(LAT2GRK), t)
    t = re.sub(r"(?<![A-Za-z])K ?(?=\d+\.\d)", "Κ", t)
    t = re.sub(r"(?<![A-Za-z])MA(?=\d+\.\d)", "ΜΑ", t)
    # 西里爾字母形近字
    t = re.sub(r"[АВЕКМНОРТХ](?=[α-ωΑ-Ω]{0,3}\d)", lambda m: "ΑΒΕΚΜΗΟΡΤΧ"["АВЕКМНОРТХ".index(m.group(0))], t)
    # δ 誤認為 ὸ/ό (τὸ1.121 → τδ1.121, Ζγό4 → Ζγδ4)
    t = re.sub(r"(?<![\w\u0370-\u1fff])([Α-Ωα-ω]{0,3})[ὸό](?=\d+\.\d+[ᵃᵇ])", r"\1δ", t)
    # 數字 1 誤認為拉丁 l (εl. 539ᵃ15 → ε1.539ᵃ15)
    t = re.sub(r"(?<![\w\u0370-\u1fff])([Α-Ωα-ω]{1,4})l(?=\d*\.\s?\d+[ᵃᵇ])", r"\g<1>1", t)
    # 縮寫中混入的拉丁小寫 (Ziδ11, Pa5, Ζu1 = Ζιι1)
    low = {"a": "α", "i": "ι", "k": "κ", "o": "ο", "t": "τ", "p": "π", "e": "ε", "v": "ν", "u": "ιι"}
    def fix(m):
        head = m.group(1).translate(LAT2GRK)
        return head + "".join(low.get(c, c) for c in m.group(2))
    t = re.sub(r"(?<![A-Za-z\u0370-\u1fff])([ΑΒΕΖΗΙΚΜΝΟΡΤΧΥABEZHIKMNOPTXY])([aikotpevuα-ω]{1,3})(?=\d+\.\d)",
               lambda m: fix(m) if re.search(r"[aikotpevu]", m.group(2)) else m.group(0), t)
    return t


CHATTY = re.compile(r"^(?:#\s*[^\n]*[一-龥][^\n]*|以下[^\n]*[：:]\s*|好的[^\n]*|\*\*左欄[^\n]*|\*\*右欄[^\n]*|"
                    r"\*\*（下接次頁）\*\*|【換頁[^】]*】)$", re.M)
CONT = re.compile(r"^\*\*[^*\n]+\*\*\s*[（(]續[^）)]*[）)]\s*", re.M)


def clean_layout(t: str) -> str:
    """OCR 的版面雜訊：說明文字、未合併的切塊分隔線 (---)、重複段落、(續) 標記"""
    t = CHATTY.sub("", t)
    t = t.replace("\u1814\u183e", "ᾠο").replace("\u1814", "")   # ᾠ 前的蒙古文雜訊 (᠔ᾠοτόκα / ᠔ᠾτόκα)
    t = CONT.sub("… ", t)                       # **λόγος**（續） → 續接
    pars = [p.strip() for p in re.split(r"\n\s*\n", t) if p.strip()]
    out = []
    join_next = False
    for p in pars:
        if re.fullmatch(r"-{3,}|\*{3,}", p):
            join_next = True
            continue
        if out and p == out[-1]:                # 切塊重疊造成的重複段落
            join_next = False
            continue
        if out and re.search(r"[^\W\d]-$", out[-1]) and re.match(r"\*\*[a-zα-ωά-ώἀ-ῷ]", p):
            # 行末斷字後，下一段的粗體其實是同一字的後半 (ἐνυ- / **παρχόντων**)
            p = re.sub(r"^\*\*(.+?)\*\*", r"\1", p)
            join_next = True
        if join_next and out and not p.startswith(("**", "#", "> ")) and not re.match(r"\d\.\s", p):
            prev = out[-1]
            if prev.endswith("-") and re.match(r"[^\W\d]", p):
                out[-1] = prev[:-1] + p
            else:
                out[-1] = prev + ("" if re.search(r"\d$", prev) and p[:1] in "ᵃᵇ" else " ") + p
        else:
            out.append(p)
        join_next = False
    return "\n\n".join(out)


def join_sigla(t: str) -> str:
    """Ζμδ 5. 680ᵃ26 → Ζμδ5.680ᵃ26 (縮寫與章號間的空格)"""
    def rep(m):
        sig = m.group(1)
        if sig == "f" or S.prefix_of(sig) or len(sig) == 1:
            return sig + m.group(2)
        return m.group(0)
    return re.sub(r"(?<![\w\u0370-\u1fff])(f|[Α-Ωα-ω]{1,4}) (\d+(?:\.\d+[ᵃᵇ]|[ᵃᵇ]))", rep, t)


# (OCR 誤讀, 正確縮寫, Bekker 頁碼範圍)：誤讀縮寫直接接章號、且頁碼落在正確書卷範圍內才改
RANGE_FIXES = [
    ("Ζμ", "Ζιι", 605, 638),   # HA ι 卷 (Ζιι) 被讀成 Ζμ；PA (Ζμ) 必帶卷號字母
    ("πο", "πδ", 876, 880),    # Probl. IV (πδ) 被讀成 Poet. (πο, 1447–1462)
    ("Ζι", "Ζιι", 605, 638),   # HA ι 卷漏掉一個 ι (Ζι3.610ᵇ29)；HA 引用必帶卷號字母
]


# β 的尾巴常被 OCR 讀成多一個 3 (Ηβ37.1107 → Ηβ7.1107)。這些書的 β 卷都不到 30 章，
# 所以 β3X 必為誤讀；Problemata β (πβ) 有 40 多章，不列入。
BETA3 = ["Ζγβ", "Ζμβ", "Ζιβ", "φτβ", "ημβ", "ηεβ", "πκβ", "πιβ", "πλβ",
         "Πβ", "Ηβ", "μβ", "ψβ", "Φβ", "Ρβ", "Μβ", "τβ", "Οβ", "Αβ"]


def fix_beta3(t: str) -> str:
    return re.sub(r"(?<![\w\u0370-\u1fff])(" + "|".join(BETA3) + r")3(\d)(?=\.\d)", r"\1\2", t)


def fix_zii(t: str) -> str:
    """Ζμ1.608ᵃ33 → Ζιι1.608ᵃ33、πο26.879ᵇ6 → πδ26.879ᵇ6 (見 RANGE_FIXES)"""
    for bad, good, lo, hi in RANGE_FIXES:
        t = re.sub(r"(?<![\wͰ-῿])" + bad + r"(?=(\d+B?)\.(\d+)[ᵃᵇ])",
                   lambda m: good if lo <= int(m.group(2)) <= hi else m.group(0), t)
    return t


def normalize(t: str) -> str:
    t = t.replace("\u00a0", " ")
    # 部分頁面 OCR 把原書的粗體書名縮寫也標成粗體：**Ρα**8.1366 → Ρα8.1366
    t = re.sub(r"\*\*((?:f|[Α-Ωα-ωϛ]{1,4}|MA|K))\*\*\s*(?=\d)", r"\1", t)
    t = clean_layout(t)
    t = t.translate(FULLWIDTH)
    t = greek_sigla(t)
    # 362 b14 -> 362ᵇ14 (部分頁面 OCR 以普通 a/b 表示 Bekker 欄)
    t = re.sub(r"(\d) ?([ab])(?=\d)", lambda m: m.group(1) + "ᵃᵇ"["ab".index(m.group(2))], t)
    t = re.sub(r"([,(] ?)([ab])(?=\d)", lambda m: m.group(1) + "ᵃᵇ"["ab".index(m.group(2))], t)
    t = re.sub(r"(\d)al\b", r"\1 al", t)
    # 1325 ᵇ31 -> 1325ᵇ31 ; ", ᵇ10" 保留
    t = re.sub(r"(\d)\s+([ᵃᵇ])(?=\d)", r"\1\2", t)
    # Πη3. 1325ᵇ31 -> Πη3.1325ᵇ31   (章節.頁碼 之間不留空)
    t = re.sub(r"(\d)\.\s+(\d+[ᵃᵇ]\d)", r"\1.\2", t)
    # f 402.1545 -> f402.1545  (fragmenta)
    t = re.sub(r"\bf\s+(\d)", r"f\1", t)
    # οβ 1348ᵃ29 -> οβ1348ᵃ29
    t = re.sub(r"([α-ωΑ-Ω])\s+(\d+[ᵃᵇ]\d)", r"\1\2", t)
    # sqq 前後
    t = join_sigla(t)
    # HA ι 49B：OCR 常寫成希臘 Β 或在句點後空格
    t = re.sub(r"(\d)\s?[ΒB]\.\s*(\d)", r"\1B.\2", t)
    t = re.sub(r"(\d)sqq", r"\1 sqq", t)
    t = greek_sigla(t)                       # 空格合併後再做一次
    t = fix_zii(t)
    t = fix_beta3(t)
    # 現代動物學注釋 (Karsch, Aubert–Wimmer)，不是亞氏書名：改回拉丁字母以免被當出處
    t = re.sub(r"(?<![\w\u0370-\u1fff])Κα\s?Ζ([ιμγ])\s?", r"KaZ\1 ", t)
    t = re.sub(r"(?<![\w\u0370-\u1fff])ΑΖ([ιμγ])\s?", r"AZ\1 ", t)
    # f. 596 → f596
    t = re.sub(r"(?<![\w])f\.\s?(\d)", r"f\1", t)
    # κ3 1061ᵇ8 → κ3.1061ᵇ8 (章與頁之間漏了句點)
    t = re.sub(r"(?<![\w\u0370-\u1fff])([Α-Ωα-ωϛ]{1,4}\d+) (\d{2,4}[ᵃᵇ]\d)", r"\1.\2", t)
    t = re.sub(r"(\d)\.\s+(\d+[ᵃᵇ]\d)", r"\1.\2", t)
    # 頁首續接標記
    t = re.sub(r"^\.\.\.\s*", "… ", t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip() + "\n"


def move_pars(txt, op):
    """搬動段落 (修正 OCR 切塊拼接順序)：
    {"move": 起始段開頭, "until": 結束段開頭 (含), "before"/"after": 目標段開頭 | "end"}"""
    ps = txt.strip().split("\n\n")
    find = lambda s, start=0: next((i for i in range(start, len(ps)) if ps[i].startswith(s)), None)
    i = find(op["move"])
    j = find(op.get("until", op["move"]), i or 0) if i is not None else None
    if i is None or j is None:
        return txt, False
    block, rest = ps[i:j + 1], ps[:i] + ps[j + 1:]
    tgt = op.get("before") or op.get("after")
    if tgt == "end":
        k = len(rest)
    else:
        k = next((x for x in range(len(rest)) if rest[x].startswith(tgt)), None)
        if k is None:
            return txt, False
        if "after" in op:
            k += 1
    return "\n\n".join(rest[:k] + block + rest[k:]) + "\n", True


# ── ȣ (ου) 連字誤認為 υ 的修復：以 LSJ 詞形表判斷 ──
_FORMS = None
OU_EXCLUDE = {"μιτυσ", "εμυσ", "ιλευσ"}       # LSJ 詞形表缺漏、實為正確的字
_GR = "αβγδεζηθικλμνξοπρστυφχψως"


def _forms():
    global _FORMS
    if _FORMS is None:
        sys.path.insert(0, str(Path(__file__).parent))
        import lexcheck
        _FORMS = lexcheck.forms()
    return _FORMS


def _plain(w):
    import unicodedata
    s = "".join(c for c in unicodedata.normalize("NFD", w) if not unicodedata.combining(c)).lower()
    return re.sub(r"[^α-ω]", "", s.replace("ς", "σ"))


def fix_ou_word(w):
    import unicodedata
    F = _forms()
    p = _plain(w)
    if len(p) < 2 or p in F or p in OU_EXCLUDE:
        return w
    letters = [(i, c) for i, c in enumerate(w) if unicodedata.normalize("NFD", c)[0].lower() in _GR]
    if len(letters) != len(p):
        return w
    for k, (i, c) in enumerate(letters):
        base = unicodedata.normalize("NFD", c)[0].lower()
        prev = unicodedata.normalize("NFD", letters[k - 1][1])[0].lower() if k else ""
        if base == "υ" and prev != "ο" and (p[:k] + "ου" + p[k + 1:]) in F:
            o = "Ο" if c.isupper() else "ο"
            u = c.lower() if c.isupper() else c
            q = p[:k] + "ου" + p[k + 1:]
            if k == 0 and not ROUGH_OU.match(q):
                # 詞首 υ 必帶粗氣符，但 ου 多為柔氣 (οὐκ, οὐσία)：改為柔氣符
                u = unicodedata.normalize("NFC", unicodedata.normalize("NFD", u).replace("\u0314", "\u0313"))
            return w[:i] + o + u + w[i + 1:]
    return w


ROUGH_OU = re.compile(r"^ου(?:τ(?!ε)|σ?$|νεκα|περ)")       # οὗτος, οὕτω, οὗ, οὕς, οὕνεκα, οὗπερ
OU_SHORT = {"τῦ": "τοῦ", "ὑκ": "οὐκ", "ὗ": "οὗ", "ὕτως": "οὕτως", "ὑδὲ": "οὐδὲ", "ὑδέ": "οὐδέ"}


def fix_bare_ou(t):
    """缺氣息符的獨立 ου/ουκ/ουχ (ȣ̓ 的符號遺失)：→ οὐ；ου ἂν、κεῖται ου ἡ、ἐξ ου 為關係詞 οὗ"""
    B, A = r"(?<![\wͰ-Ͽἀ-῿])", r"(?![\wͰ-Ͽἀ-῿])"
    t = re.sub(B + r"ου(?= ἂν)", "οὗ", t)
    t = t.replace("κεῖται ου ἡ καρδία", "κεῖται οὗ ἡ καρδία").replace("ἐξ ου ὄφεως", "ἐξ οὗ ὄφεως")
    t = re.sub(B + r"ου([κχ]?)" + A, r"οὐ\1", t)
    return t


def fix_ou(t):
    t = fix_bare_ou(t)
    t = re.sub(r"(?<![\u0370-\u03ff\u1f00-\u1fff])(" + "|".join(OU_SHORT) + r")(?![\u0370-\u03ff\u1f00-\u1fff])",
               lambda m: OU_SHORT[m.group(1)], t)
    return re.sub(r"[\u0370-\u03ff\u1f00-\u1fff]+", lambda m: fix_ou_word(m.group(0)), t)


def pages(spec):
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += range(int(a), int(b or a) + 1)
    return out


if __name__ == "__main__":
    force = "-f" in sys.argv
    args = [a for a in sys.argv[1:] if a != "-f"]
    # 已對照圖檔校對的頁 (PROOFREADING.md 的「已校頁」)：即使 -f 也不覆蓋
    done = set(re.findall(r"page-(\d{3})", (SRC.parent / "PROOFREADING.md").read_text(encoding="utf-8")
                          .split("<!-- done -->")[1].split("<!-- /done -->")[0]))
    for p in pages(args[0]):
        dst = SRC / f"page-{p:03d}.md"
        if f"{p:03d}" in done:
            print("skip (proofread)", dst.name)
            continue
        if dst.exists() and not force:
            print("skip", dst.name)
            continue
        txt = fix_ou(normalize((OCR / dst.name).read_text(encoding="utf-8")))
        hit = {}
        for op in FIXES.get(dst.stem, []):
            if isinstance(op, dict):
                txt, ok = move_pars(txt, op)
                if not ok:
                    print(f"WARNING {dst.name}: move {op} not applied")
                continue
            old, new = op
            if old in txt:
                txt = txt.replace(old, new)
                hit[new] = True
            else:
                hit.setdefault(new, False)
        for new, ok in hit.items():
            if not ok:
                print(f"WARNING {dst.name}: fix → {new!r} not applied (pattern not found)")
        dst.write_text(txt, encoding="utf-8")
        print("wrote", dst.name)
