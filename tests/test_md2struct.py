"""md2struct 出處解析與 sigla 的回歸測試。

執行: python3 -m unittest discover tests     (純標準庫，雲端也可跑)

每個案例取自原書的寫法 (多數直接摘自 src/)。出處以精簡字串比對：
  sig+章.頁欄行[-迄][?]   ? = 依 Bekker 頁碼推定書名 (guess)
改解析器時，若某案例的「正確答案」本身要改，請先對原書確認。
全書層級的變化請另用 tools/parsediff.py 檢查。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import md2struct as M  # noqa: E402
import sigla as S  # noqa: E402


def fmt(c):
    s = "%s%s.%s%s%s" % (c["sig"] or "", c["ch_eff"] or "", c["page"] or "", c["col"] or "", c["line"] or "")
    if c["to"]:
        s += "-" + c["to"]
    if c.get("guess"):
        s += "?"
    return s


def parse(text):
    """→ [(用例文字, [出處...]) ...]，每次用新的 Resolver (即新詞條)"""
    return [(it["text"], [fmt(c) for c in it["cites"]]) for it in M.to_items(text, M.Resolver())]


def cites(text):
    return [c for _, cs in parse(text) for c in cs]


class Inheritance(unittest.TestCase):
    """承前省略：書名、卷、章、頁、欄依次沿用前一筆"""

    def test_book_and_chapter(self):
        self.assertEqual(cites("ἔχειν μέγεθος Πδ16.1300ᵇ23. Ζια5.490ᵃ17, 18. β1.499ᵃ11. ε2.540ᵃ4. 5.540ᵇ11."),
                         ["Πδ16.1300b23", "Ζια5.490a17", "Ζια5.490a18", "Ζιβ1.499a11", "Ζιε2.540a4", "Ζιε5.540b11"])

    def test_column_and_line(self):
        self.assertEqual(cites("ἀετός Ζιι32.619ᵃ20, 23. 33.619ᵇ17. ᵇ5. ι34.619ᵃ20, 27, ᵇ25, 34."),
                         ["Ζιι32.619a20", "Ζιι32.619a23", "Ζιι33.619b17", "Ζιι33.619b5",
                          "Ζιι34.619a20", "Ζιι34.619a27", "Ζιι34.619b25", "Ζιι34.619b34"])

    def test_page_only(self):
        self.assertEqual(cites("a Πβ8.1267ᵇ33. 1268ᵃ1."), ["Πβ8.1267b33", "Πβ8.1268a1"])

    def test_book_letter_resolved_by_page(self):
        # γ 單獨不是書名縮寫：依頁碼 754 (GA) 補成 Ζγγ
        self.assertEqual(cites("κινεῖ Φθ3.253ᵃ31. cf ᵃ26. γ3.754ᵇ1."),
                         ["Φθ3.253a31", "Φθ3.253a26", "Ζγγ3.754b1"])

    def test_book_letter_same_work(self):
        self.assertEqual(cites("a Ηα1.1094ᵃ1. ε7.1131ᵃ1."), ["Ηα1.1094a1", "Ηε7.1131a1"])
        self.assertEqual(cites("φιλία Ηθ1.1155ᵃ3. ι2.1164ᵇ22. ηεη6.1240ᵃ8. 2.1236ᵇ33."),
                         ["Ηθ1.1155a3", "Ηι2.1164b22", "ηεη6.1240a8", "ηεη2.1236b33"])

    def test_new_entry_resets(self):
        self.assertEqual(cites("a ε2.540ᵃ4."), ["Ζιε2.540a4"])        # 無前文：依頁碼


class Forms(unittest.TestCase):

    def test_ranges(self):
        self.assertEqual(cites("ἔχειν Πε9.1309ᵃ33-36. ἀρχή Ζιζ6.563ᵃ17-ᵇ5."),
                         ["Πε9.1309a33-36", "Ζιζ6.563a17-b5"])

    def test_comma_line_then_page(self):
        # Bonitz 體例：逗號後不換章 → ", 36.1073ᵃ2" = 第 36 行；1073ᵃ2
        self.assertEqual(cites("a Μλ7.1072ᵇ13, 36.1073ᵃ2."), ["Μλ7.1072b13", "Μλ7.1072b36", "Μλ7.1073a2"])

    def test_split_chapter_and_page(self):
        # "Ζμ15. 616ᵇ10"：章與頁被拆開 → 一筆；頁碼屬 HA ι 卷 → Ζιι
        self.assertEqual(cites("λέγει Ζμ15. 616ᵇ10."), ["Ζιι15.616b10?"])

    def test_chapter_only(self):
        self.assertEqual(parse("ποσαχῶς λέγεται Μδ23 Bz."), [("ποσαχῶς λέγεται", ["Μδ23."])])

    def test_chapter_suffix_B(self):
        self.assertEqual(cites("a Ζιι49B.632ᵇ21."), ["Ζιι49B.632b21"])

    def test_fragment_and_problems(self):
        self.assertEqual(cites("ἔχειν ἐπιμέλειαν f412.1546ᵇ27."), ["f412.1546b27"])
        self.assertEqual(cites("ἐπαγωγή πκη7.950ᵃ3."), ["πκη7.950a3"])

    def test_unsure_brackets_removed(self):
        self.assertEqual(cites("a 【Πβ8.1267ᵇ33】."), ["Πβ8.1267b33"])

    def test_qualifiers(self):
        it = M.to_items("a Πβ8.1267ᵇ33 sqq. Ργ1.1403ᵇ6 Bk² Vhl. Μλ7.1072ᵇ23 Bz.", M.Resolver())
        self.assertEqual([c["quals"] for c in it[0]["cites"]], [["sqq"], ["Bk²", "Vhl"], ["Bz"]])

    def test_note_and_cf(self):
        it = M.to_items("ἀπορίαν Ηι2.1164ᵇ22 (cf α11.1100ᵃ22). τὸ ἔμβρυον Ζγβ4.740ᵃ37. cf ᵃ26.", M.Resolver())
        self.assertEqual(it[0]["cites"][0]["note"], "cf α11.1100ᵃ22")
        self.assertEqual([fmt(c) for c in it[1]["cites"]], ["Ζγβ4.740a37", "Ζγβ4.740a26"])
        self.assertEqual(it[1]["cites"][1]["pre"], "cf")


class Guess(unittest.TestCase):
    """縮寫與 Bekker 頁碼不合時依頁碼推定書名"""

    def test_confusable_capitals(self):
        self.assertEqual(cites("a Ρβ3.1276ᵃ8."), ["Πβ3.1276a8?"])         # Ρ↔Π

    def test_same_initial(self):
        self.assertEqual(cites("ψευδές Ζγ3.616ᵇ10."), ["Ζιι3.616b10?"])     # Ζγ→Ζι(ι)

    def test_metaphysics_alpha(self):
        self.assertEqual(cites("a Α1.981ᵃ1."), ["ΜΑ1.981a1?"])

    def test_consistent_not_guessed(self):
        self.assertEqual(cites("ἀτμίς μβ4.360ᵇ14. Μα1.981ᵃ1."), ["μβ4.360b14", "Μα1.981a1"])


class NotCitations(unittest.TestCase):
    """不該當成亞里斯多德出處的數字"""

    def test_homer(self):
        self.assertEqual(parse("Ἀντιγόνη Hom Ε 661 Ργ11.1411ᵃ2."),
                         [("Ἀντιγόνη Hom Ε 661", ["Ργ11.1411a2"])])
        self.assertEqual(parse("a Hom Il 2, 204 Πγ16.1287ᵃ7."), [("a Hom Il 2, 204", ["Πγ16.1287a7"])])

    def test_parenthesised_kept_in_text(self):
        self.assertEqual(parse("a (Ηα13.1102ᵇ27) Ζγβ4.740ᵃ37."), [("a (Ηα13.1102ᵇ27)", ["Ζγβ4.740a37"])])

    def test_bare_page_other_work(self):
        # 說明文字後的裸頁碼只在與前一書名相符時才承前
        self.assertEqual(parse("οἷον Πα2.1253ᵃ18 et 575ᵇ15."),
                         [("οἷον", ["Πα2.1253a18"]), ("et 575ᵇ15", [])])

    @unittest.expectedFailure
    def test_homer_book_line_list(self):
        # 〈Ὅμηρος〉詞條 (page-507) 的奧德賽卷行號 σ136 目前被當成 Vent. 第 136 章
        self.assertEqual(cites("— σ136. ψγ3.427ᵃ25."), ["ψγ3.427a25"])


class KnownGaps(unittest.TestCase):

    @unittest.expectedFailure
    def test_capital_chapter_only(self):
        # page-305〈ἔχειν〉：Κ15 Wz (Cat. 第 15 章) 未解析，被併入下一則用例文字
        self.assertEqual(parse("ποσαχῶς λέγεται Μδ23 Bz. Κ15 Wz. τὸ ἔχειν Κ4.2ᵃ3.")[1][0], "τὸ ἔχειν")


class Sigla(unittest.TestCase):

    def test_longest_prefix(self):
        self.assertEqual(S.prefix_of("πκη"), "π")
        self.assertEqual(S.prefix_of("πο"), "πο")
        self.assertEqual(S.prefix_of("Ζιι"), "Ζι")
        self.assertEqual(S.prefix_of("ηεβ"), "ηε")
        self.assertIsNone(S.prefix_of("γ"))

    def test_split_works(self):
        self.assertEqual(S.work_name("Αα"), "APr.")
        self.assertEqual(S.work_name("Αγ"), "APo.")
        self.assertEqual(S.work_name("τθ"), "Top.")
        self.assertEqual(S.work_name("τι"), "SE")

    def test_page_ranges(self):
        self.assertEqual([w[2] for w in S.works_for_page(1094)], ["EN"])
        self.assertEqual([w[2] for w in S.works_for_page(468)], ["Juv.", "VM"])
        self.assertEqual(S.works_for_page(2000), [])

    def test_ranges_ordered(self):
        for a, b in zip(S.WORKS, S.WORKS[1:]):
            self.assertLessEqual(a[3], a[4], a)
            self.assertLessEqual(a[3], b[3], (a, b))

    def test_diogenes_loc(self):
        self.assertEqual(S.diogenes_loc("EN", 1094, "a", "1-3"), "010:1094a:1")
        self.assertEqual(S.diogenes_loc("MM", 1182, "a", "1", sig="ημα", ch="4"), "022:1:4")
        self.assertEqual(S.diogenes_loc("fr.", 1500, "a", "1"), "")


if __name__ == "__main__":
    unittest.main()
