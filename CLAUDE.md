# Index Aristotelicus 校對專案 — Claude 須知

使用者以繁體中文溝通，回覆也用繁體中文。

## 專案是什麼

Bonitz《Index Aristotelicus》(1870) 的 OCR 轉寫校對，並轉成結構化資料 (`data/entries.json`) 與螢幕閱讀用 PDF (`struct.tex`)。
流程與底稿標記見 `README.md`；**校對方法、已校頁、下一批、系統性錯誤見 `PROOFREADING.md`，開工前先讀它**，再看 `git log --oneline | head`。

## 固定約定

- **`src/page-NNN.md` 是主檔**，直接改它。**絕對不要跑 `tools/normalize.py -f`** (會用 OCR 原稿覆蓋全書修正)。
- **照原書轉寫，不替 Bonitz 校勘**。原書本身的誤植照錄，並緊接著加 `<!-- Bz: 應為 … -->` (不確定寫 `<!-- Bz: ? -->`)。看不清的字用 `【】`。
- 使用者說「執行一段」= 校對**下一批 5 頁** (從 `PROOFREADING.md`「下一批」開始)，結束時：
  1. 頁碼加入「已校頁」、「批次紀錄」加一列、更新「下一批」、新的系統性錯誤寫入表格
  2. 校對中發現會重複出現的 OCR 錯誤型態 → 同一批內在全書 `src/` 搜尋並修正 (只改有把握的；已校頁也要一併檢查)，寫進批次紀錄
  3. `python3 tools/md2struct.py 3-878` 確認能解析 (約 10 秒)
  4. 一批一個 commit，訊息如 `校對 page-058～062；全書 …`
- 改詞條 (粗體 lemma) 拼字時，同步改 `src/glosses.tsv` 第一欄。
- `src/glosses.tsv` 的中譯是「先求有」的粗略版本，使用者會自己修；不要主動大改。

## 在 cloud session (無本機環境) 工作時

本機與雲端的差別：

| 項目 | 本機 | 雲端 |
|---|---|---|
| 掃描圖 | `../split_out/page-NNN_{1L,2R}_{1,2,3}.png` | **`scans/`** (同檔名，4 階灰度壓縮版，只收部分頁) |
| `md2struct.py`、`audit.py`、`find_unbolded.py` | 可 | 可 (純 Python 標準庫；CJK 字型缺時自動略過) |
| `latexmk -xelatex struct.tex` | 可 (約 1 小時) | **不可** (缺 `myfonts`/`mylangs` 與字型)，不要嘗試 |
| `check_diogenes.py` | 需 localhost:8888 | **不可** |
| `lexcheck.py` | 需本機 Diogenes 詞形表 | **不可**；`data/lexcheck.tsv` 是既有結果，可直接讀 |
| `normalize.py` | 需 `../pages_out/` | 不可 (也不該再用) |

- 看圖：用 Read 讀 `scans/` 的 PNG；字形看不清時用 PIL 裁切放大 (`pip install pillow` 若缺)，放大圖存到暫存目錄，不要 commit。
- **`scans/` 裡沒有下一批的頁面時就停下**，告訴使用者在本機執行 `python3 tools/export_scans.py <起>-<迄>` 並 push；不要在沒有圖檔的情況下「校對」。
- 不要 commit 編譯產物或 `struct/`、`data/entries.json` (已在 `.gitignore`)。
- 做完一批就 commit 並 push 到目前分支，使用者會在本機 pull 後重編 PDF。

## 圖檔位置

- `scans/` 只是給雲端用的工作副本。已校完的頁面可以從 `scans/` 刪掉 (歷史裡仍在)，但不刪也沒關係。
- 新增頁面範圍 (本機)：`python3 tools/export_scans.py 108-157`，約 0.9 MB/頁。
