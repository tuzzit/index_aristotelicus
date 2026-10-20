#!/usr/bin/env python3
"""把 data/entries.json 中的希臘文引文與 TLG 原文逐字比對，列出可疑字。

原文讀自 data/tlg/aristotle.tsv (tools/build_tlg.py 從本機 TLG-E 匯出；授權限制，不在 git 中)。
對每個 item，取其文字中最後一段希臘文 (前面夾帶的出處之後)，以出處行為中心取前 3 行至後 6 行原文
(item 有多個出處時取最相符者)，用不計重音的字形對齊，再逐字比較：
  ocr    字形不同，且差異全是本書常見的 OCR 混淆 (ȣ↔ω/ο/η、σ↔τ…)：優先檢查
  word   其他字形差異：多為 Bonitz 改寫 (詞尾、語序) 或版本異文，偶爾也是 OCR 錯
  accent 只有重音/氣息/下寫 ι 不同 (已忽略 grave/acute 之別)
只是「候選清單」：照原書轉寫的原則不變，最後一律對照掃描圖判斷。
TLG 各作品所用版本見 data/tlg/editions.tsv；非 Bekker 版本 (如 Physica 用 Ross) 的差異較多。
用法: python3 quotecheck.py [entries.json] [頁碼範圍 如 123-127]
輸出 data/quotecheck.tsv
"""
import json
import re
import sys
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import sigla as S  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TLG = ROOT / "data" / "tlg" / "aristotle.tsv"
GREEK = re.compile(r"[Ͱ-Ͽἀ-῿̀-ͯ᾽']+")
# 夾在 item 文字中的出處 (如 `Ζγδ4.773ᵃ18.`)，用來切出最後一段引文
CITE = re.compile(r"\S*\d+[ᵃᵇ]\d+\S*")
BEFORE, AFTER = 3, 6          # 出處行前後各取幾行原文


def norm(w, accents):
    """accents=False：只留字母 (並統一拼法異體)；True：保留氣息、重音 (grave→acute)、下寫 ι。"""
    w = unicodedata.normalize("NFD", w.replace("ς", "σ").replace("ϲ", "σ")).lower()
    keep = {"̓", "̔", "́", "͂", "ͅ", "̈"} if accents else set()
    w = w.replace("̀", "́")
    w = "".join(c for c in w if ("α" <= c <= "ω") or c in keep)
    return w if accents else spelling(w)


def plain_letters(w):
    return "".join(c for c in unicodedata.normalize("NFD", w.replace("ς", "σ")).lower() if "α" <= c <= "ω")


# 版本間常見的拼法差異，視為相同 (γίνεσθαι/γίγνεσθαι、γινώσκειν/γιγνώσκειν、ἐστὶ/ἐστὶν)
def spelling(w):
    w = re.sub(r"γιν(?=[ωοεη])", "γιγν", w)
    return re.sub(r"(σι|τι|ε)ν$", r"\1", w)


def words(text):
    return [w for w in (m.group(0).strip("'᾽") for m in GREEK.finditer(text)) if norm(w, False)]


def load_tlg():
    """→ {work: [(page, col, line, text), ...] 依序}, {(work, page, col, line): 序號}"""
    if not TLG.exists():
        sys.exit(f"{TLG} 不存在：先在本機執行 python3 tools/build_tlg.py")
    lines = defaultdict(list)
    for row in TLG.read_text(encoding="utf-8").splitlines():
        w, p, c, l, t = row.split("\t", 4)
        lines[w].append((int(p), c, int(l), t))
    index = {}
    for w, ls in lines.items():
        ls.sort()
        for k, (p, c, l, _) in enumerate(ls):
            index[(w, p, c, l)] = k
    return lines, index


def source(lines, index, w, page, col, line):
    """出處行前後的原文字列 (斷字連字號接回) 與出處行首字在其中的位置；找不到該行回傳 None。"""
    k = index.get((w, page, col, line))
    if k is None:
        return None
    ls = lines[w][max(0, k - BEFORE):k + AFTER + 1]
    t = re.sub(r"(\w)-\s+(\w)", r"\1\2", " ".join(x[3] for x in ls))
    before = re.sub(r"\S+-$", "", " ".join(x[3] for x in ls[:min(k, BEFORE)]))
    return words(t), len(words(before))


def quote_of(item):
    segs = CITE.split(item["text"])
    return words(segs[-1] if segs else item["text"])


# 本書 OCR 常見的字形混淆 (見 PROOFREADING.md 系統性錯誤)：ȣ (ου) 被讀成 ω/ο/η/ε/υ，σ↔τ，α/ε/ο 互換
CONFUSIONS = {frozenset(p) for p in [("ου", "ω"), ("ου", "ο"), ("ου", "η"), ("ου", "ε"), ("ου", "υ"),
                                     ("ου", "ι"), ("ου", "α"), ("σ", "τ"), ("α", "ε"), ("ε", "ο"),
                                     ("α", "ο"), ("ι", "τ"), ("ι", "η"), ("β", "κ"), ("π", "τ")]}


def ocr_like(x, y):
    """兩字 (不計重音) 的差異是否全由 CONFUSIONS 構成 (另有混淆時，詞尾多一個 ν/ς 也算)。"""
    x, y = norm(x, False), norm(y, False)
    if x == y:
        return False
    if x.rstrip("νσ") == y.rstrip("νσ"):   # 只差詞尾 ν/ς：長字多為 Bonitz 改格 (θρεπτικὴ/-ὴν)，短字多為 OCR (νοῦς/νοῦ)
        return len(x) <= 4
    for op, i1, i2, j1, j2 in SequenceMatcher(None, x, y, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        if frozenset((x[i1:i2], y[j1:j2])) in CONFUSIONS:
            continue
        if op in ("insert", "delete") and max(i2, j2) == max(len(x), len(y)) and (x[i1:i2] + y[j1:j2]) in ("ν", "σ"):
            continue
        # ȣ 與單一母音互換時 difflib 可能拆成 replace + insert，例 του/τω
        if {x[i1:i2], y[j1:j2]} <= {"ο", "υ", "ω", "η", "ε", ""} and len(x[i1:i2] + y[j1:j2]) <= 3:
            continue
        return False
    return True


def similar(x, y):
    return SequenceMatcher(None, norm(x, False), norm(y, False), autojunk=False).ratio()


def align(q, src, center):
    """在 src 中找與 q 最相符的區段，回傳逐字對照 [(引文字, 原文字)] 與相符率。

    先以完全相同的字 (不計重音) 為錨點定位 (同分時取最接近出處行者，center 為出處行首字的位置)；
    錨點之間沒配上的引文字，再到相鄰錨點之間的原文 (引文頭尾則往外多看 8 個字) 找最像的字：
    符合 OCR 混淆者優先，否則相似度 ≥ 0.55 才配對。
    如此 Bonitz 刪節、改寫處 (原文多出的字) 不會干擾，但 `φυτικὴ`/`φυσικὴν` 這類近形字會配上。
    """
    a = [norm(w, False) for w in q]
    sn = [norm(w, False) for w in src]
    best = None
    for start in range(0, max(1, len(src) - len(q) + 1)):
        sm = SequenceMatcher(None, a, sn[start:start + len(q) + 8], autojunk=False)
        blocks = [(i, start + j, n) for i, j, n in sm.get_matching_blocks() if n]
        m = sum(n for _, _, n in blocks)
        key = (m, -abs(blocks[0][1] - center) if blocks else 0)
        if not best or key > best[0]:
            best = (key, blocks)
    if not best or not best[0][0]:
        return fuzzy(q, src, center)
    (m, _), blocks = best
    # 落單的短虛詞錨點 (如 ἡ、τὸ) 若與其他錨點的距離遠超過引文中的距離，多半是對到別處的同一個字
    if len(blocks) > 1:
        keep = []
        for k, (i, j, n) in enumerate(blocks):
            others = [b for b in blocks if b is not blocks[k]]
            near = min(abs((j - j2) - (i - i2)) for i2, j2, _ in others)
            if n == 1 and len(a[i]) <= 3 and near > 4:
                continue
            keep.append((i, j, n))
        blocks = keep or blocks
        m = sum(n for _, _, n in blocks)
    match = {}
    for i, j, n in blocks:
        for k in range(n):
            match[i + k] = j + k
    used = set(match.values())
    pairs = []
    for i in range(len(q)):
        if i in match:
            pairs.append((q[i], src[match[i]]))
            continue
        prev = max((k for k in match if k < i), default=None)
        nxt = min((k for k in match if k > i), default=None)
        lo = match[prev] + 1 if prev is not None else match[nxt] - 8
        hi = match[nxt] if nxt is not None else match[prev] + 9
        cand = [(ocr_like(q[i], src[j]), similar(q[i], src[j]), j)
                for j in range(max(0, lo), min(len(src), hi)) if j not in used]
        if cand:
            o, r, j = max(cand)
            if o or r >= 0.55:
                pairs.append((q[i], src[j]))
                used.add(j)
    # 相符率計入近形配對：Bonitz 調動語序、或錯字多的短引文 (錨點少) 不致被誤判為對不上
    return pairs, len(pairs) / max(1, len(a))


def fuzzy(q, src, center):
    """完全沒有相同字時 (短引文且每個字都錯，如 `τῷ βίῳ`)：在出處行附近找逐字最像的連續區段。"""
    best = None
    for start in range(max(0, center - 15), min(len(src) - len(q), center + 15) + 1):
        pairs = [(x, y) for x, y in zip(q, src[start:start + len(q)]) if ocr_like(x, y) or similar(x, y) >= 0.6]
        key = (len(pairs), -abs(start - center))
        if not best or key > best[0]:
            best = (key, pairs)
    if not best or best[0][0] < max(2, len(q) / 2):
        return [], 0
    return best[1], best[0][0] / len(q)


def main():
    ej = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "entries.json"
    rng = sys.argv[2] if len(sys.argv) > 2 else "3-878"
    lo, hi = (int(x) for x in rng.split("-"))
    lines, index = load_tlg()
    rows, scores, nosrc = [], [], 0
    for e in json.loads(ej.read_text(encoding="utf-8")):
        pg = e["src"]                       # 詞條起始的 src/page-NNN.md
        if not lo <= pg <= hi:
            continue
        for b in e["body"]:
            for it in b.get("items", []):
                q = quote_of(it)
                if len(q) < 2 or not it["cites"]:
                    continue
                best = None
                for c in it["cites"][:3]:
                    w = S.TLG.get(c["work"])
                    if not (w and c["page"] and c["col"] and c["line"]) or c["work"] == "MM":
                        continue
                    ln = int(str(c["line"]).split("-")[0])
                    got = source(lines, index, w, c["page"], c["col"], ln)
                    if not got:
                        continue
                    pairs, score = align(q, *got)
                    if not best or score > best[0]:
                        best = (score, pairs, f'{c["sig"]}{c["ch"] or ""}.{c["page"]}{c["col"]}{c["line"]}')
                if not best:
                    nosrc += 1
                    continue
                score, pairs, cite = best
                scores.append(score)
                if score < 0.4:          # 相符不到四成：多半是出處錯、改寫或版本差太大，不列
                    continue
                for x, y in pairs:
                    if norm(x, False) != norm(y, False):
                        kind = "ocr" if ocr_like(x, y) else "word"
                    elif norm(x, True) != norm(y, True) and plain_letters(x) == plain_letters(y):  # 拼法異體不列
                        kind = "accent"
                    else:
                        continue
                    rows.append((pg, e["lemma"], cite, kind, x, y, score, " ".join(q)))
    order = {"ocr": 0, "word": 1, "accent": 2}
    rows.sort(key=lambda r: (r[0], order[r[3]]))
    with (ROOT / "data" / "quotecheck.tsv").open("w", encoding="utf-8") as f:
        f.write("page\tlemma\tcite\tkind\tbonitz\ttlg\tmatch\tquote\n")
        for r in rows:
            f.write("\t".join([f"page-{r[0]:03d}", r[1], r[2], r[3], r[4], r[5], f"{r[6]:.2f}", r[7]]) + "\n")
    good = sum(s >= 0.4 for s in scores)
    print(f"{good}/{len(scores)} quotes aligned (≥40%), {nosrc} without TLG line; "
          + ", ".join(f"{sum(r[3] == k for r in rows)} {k}" for k in order))


if __name__ == "__main__":
    main()
