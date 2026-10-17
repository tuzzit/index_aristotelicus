# Index Aristotelicus — LaTeX 重排

## 流程

```
pages_out/page-NNN.md   (OCR 原稿，不改動)
   │  python3 tools/normalize.py 13-22      機械正規化 (不覆蓋已存在的檔案, -f 強制)
   ▼
src/page-NNN.md         校對底稿 ← 人工/對照圖檔校對都改這裡
   │  python3 tools/md2struct.py 3-878     轉結構化資料 (data/entries.json, struct/*.tex 為產物)
   ▼
struct/*.tex
   │  latexmk -xelatex struct.tex
   ▼
struct.pdf
```

校對進度與工作方式見 `PROOFREADING.md`。舊版仿原書版式 (main.tex, md2tex.py, body/) 已封存於 `_archive_main/`。

原書頁碼 = 檔案頁碼 − 2 (page-003 = p. 1)。

## 底稿標記

| 標記 | 意義 |
|---|---|
| `# Α` | 字母分節 |
| `**lemma,** …` (段首) | 詞條，疏排 + 懸掛縮排，進入書眉 |
| `> …` | 詞條內分項 (如 `> 2. *species* …`)，首行縮排 |
| `— **ἀγαπητός.**` (段中) | 段中疏排的副詞條 (副詞、衍生詞等) |
| `… ` (頁首) | 續接上一頁最後一段 |
| `*notio*` | 斜體 |
| `【x】` | 不確定讀法，PDF 中以黃底標出 |

## normalize.py 自動處理的 OCR 問題

- `1325 ᵇ31` → `1325ᵇ31`；`Πη3. 1325ᵇ31` → `Πη3.1325ᵇ31`；`f 402` → `f402`
- 部分頁面用普通 `a`/`b` 表 Bekker 欄 (如 page-011/012/018) → `ᵃ`/`ᵇ`
- 書名縮寫誤用拉丁大寫 (`Zμγ`, `Pβ`, `K8.`) 或全形 `Ａ` → 希臘大寫

## 人工校對時常見的 OCR 錯誤 (p.1–10 實例)

- **ȣ 連字 (οὐ) 誤讀為 καὶ**：`καὶ σαφής` 應為 `οὐ σαφής`，`καθ' ὁ` 應為 `οὐθ' ὁ`
- **Ζιι (HA 第 ι 卷) 誤作 Ζμ**：`Ζμ34.619` → `Ζιι34.619`
- 書名誤認：`Πθ` ↔ `Πδ`、`νεη` → `ηεη`、`Ρφ` → `Ρα`、`χ6` → `κ6`
- 多出的數字：`Μβ34.999` → `Μβ4.999`、`Ρβ36` → `Ρβ6`
- 氣息符：`ἀδρός` → `ἁδρός`、`ἀγνός` → `ἁγνός`、`ᾄδης` → `ᾅδης`
- 段中疏排副詞條 (`— ἀδεῶς`, `— ἀγχίνως`) 常被漏標粗體
- 頁首續接文字被誤標為詞條 (`**τῶν ἀγώνων**`、`**b**19.`)
- 跨頁斷字 (`ἀδιανοητό-` / `τερον`) 須合併
- **page-005 開頭有一段幻覺文字** (ἀκμάζει / ἀκμή / ἀκοή，屬於後面的詞條)，已刪除；其他頁也可能有，留意與前後頁字母順序不符的段落

## 結構化版本 (struct.tex) — 目前採用的方向

不保留原書版式，把每個詞條拆成結構元素呈現：

```
python3 tools/md2struct.py 3-12      # src/ → data/entries.json + struct/*.tex
latexmk -xelatex struct.tex
```

- `tools/sigla.py`：Bonitz 書名縮寫表與 Bekker 頁碼範圍 (依原書卷首縮寫表)
- `tools/md2struct.py`：解析詞條 → 分項 (sense) / 副詞條 (sub) / 用例組 (group，原書 — 分隔) / 用例 (item = 原文片段＋出處)
  - 出處依 Bonitz 承前省略體例補全 (`ε7` 承 `Ηα1` → `Ηε7`；逗號後不換章)，並以 Bekker 頁碼核對書名
- `data/entries.json`：同一份結構的機器可讀版本，供搜尋/自動化使用
- 版面巨集都在 `struct.tex` (\attest, \cit, \sense, \sublemma, \rel …)，可單獨調整樣式

## 全書 (2026-10 起)

```
# (勿再跑 normalize.py -f：src/ 已是主檔，見 PROOFREADING.md)
python3 tools/md2struct.py 3-878                # → data/entries.json, struct/*.tex (約 10 秒)
python3 tools/check_diogenes.py 6               # 逐一檢查 Diogenes 連結 (需伺服器；可中斷續跑)
latexmk -xelatex struct.tex                     # 單檔全書，約 1 小時
```

- `src/ocr_fixes.json`：人工修正表 (正規化後套用)；改這裡比改 src/page-*.md 不易被 `-f` 覆蓋
- `src/glosses.tsv`：每個詞條的簡短中譯 (`lemma<TAB>中譯`)，先求有、未經細究；直接修改後重跑 md2struct + latexmk 即可
- `data/diogenes_check.json`：連結檢查結果。`fail` 的連結不輸出，`alt` 改連到最近可用的行
- `data/audit.tsv` (`tools/audit.py`)、`data/diagnostics.tsv`：待對照圖檔核對的疑點
- 出處右上 `?`：原書縮寫與 Bekker 頁碼不合，書名依頁碼推定 (多為 OCR 誤讀)
- 詞條索引已取消 (約 60 頁)：以 PDF 書籤 (字母 → 詞條) 與全文搜尋代替
- `data/diogenes_problems.tsv`：連結檢查為 fail / near 的出處 (含詞條與 Bonitz 頁)，多半是 OCR 誤讀造成書名或頁碼錯，待對照圖檔
- `tools/export_scans.py`：把 `../split_out/` 的圖塊壓縮複製到 `scans/`，供沒有本機檔案的 cloud session 對照 (見 `CLAUDE.md`)
- `data/ocr_odd_chars.tsv`：底稿中字型沒有的怪字元 (OCR 雜訊，如 Vedic 符號、組合附加符號)，附上下文
- 詞條中譯中，主 CJK 字型缺的罕用字自動改用 `\rare{}` (Noto Sans CJK TC)
