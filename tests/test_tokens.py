"""Лексер игровых кодов: защита, восстановление, валидация."""

from __future__ import annotations

import unittest

from ck3loc.core.tokens import (
    code_signature,
    protect,
    restore,
    tokenize,
    validate_translation,
)


class TestTokenizer(unittest.TestCase):
    def test_all_kinds(self):
        v = "@icon!Text $KEY$ [Char.GetName] #T bold#! line\\nnext"
        kinds = [t.kind for t in tokenize(v)]
        self.assertEqual(
            kinds,
            ["icon", "text", "dollar", "text", "bracket", "text",
             "fmt_open", "text", "fmt_close", "text", "newline", "text"],
        )

    def test_nested_brackets(self):
        v = "[Concept('realm_capital', GetPlayer.MakeScope.Var('x'))] rest"
        tokens = tokenize(v)
        self.assertEqual(tokens[0].kind, "bracket")
        self.assertTrue(tokens[0].text.endswith("'))]"))

    def test_unclosed_dollar_is_text(self):
        tokens = tokenize("100$ price")
        self.assertTrue(all(t.kind == "text" for t in tokens))


class TestProtectRestore(unittest.TestCase):
    def test_roundtrip(self):
        v = "@epe_icon_epe_rule!EPE: Enclosed Helmets for $ruler$"
        p = protect(v)
        self.assertNotIn("@", p.text)
        self.assertNotIn("$", p.text)
        restored, problems = restore(p.text, p.mapping)
        self.assertEqual(restored, v)
        self.assertEqual(problems, [])

    def test_translated_text_keeps_marks(self):
        p = protect("@icon!EPE: Enclosed Helmets")
        translated = p.text.replace("EPE: Enclosed Helmets", "EPE: Закрытые шлемы")
        restored, problems = restore(translated, p.mapping)
        self.assertEqual(restored, "@icon!EPE: Закрытые шлемы")
        self.assertEqual(problems, [])

    def test_lost_mark_detected(self):
        p = protect("$A$ and $B$")
        broken = p.text.replace("⟦T2⟧", "")
        _restored, problems = restore(broken, p.mapping)
        self.assertTrue(any("потерян маркер" in x for x in problems))

    def test_unknown_mark_detected(self):
        p = protect("$A$")
        _r, problems = restore(p.text + " ⟦T9⟧", p.mapping)
        self.assertTrue(any("незнакомый маркер" in x for x in problems))


class TestValidation(unittest.TestCase):
    def test_ok(self):
        s = "$GOLD$ [ROOT.Char.GetName] pays #P well#!\\nDone"
        t = "$GOLD$ [ROOT.Char.GetName] платит #P хорошо#!\\nГотово"
        self.assertEqual(validate_translation(s, t), [])

    def test_missing_dollar(self):
        errs = validate_translation("$A$ text", "текст")
        self.assertTrue(any("$…$" in e for e in errs))

    def test_changed_bracket(self):
        errs = validate_translation("[A.GetName]", "[B.GetName]")
        self.assertTrue(any("[…]" in e for e in errs))

    def test_unbalanced_fmt(self):
        errs = validate_translation("#T x#! y", "#T х y")
        self.assertTrue(errs)

    def test_real_newline_forbidden(self):
        errs = validate_translation("a\\nb", "а\nб")
        self.assertTrue(any("перенос строки" in e for e in errs))

    def test_signature_counts_duplicates(self):
        sig = code_signature("$A$ $A$ $B$")
        self.assertEqual(sorted(sig["dollar"]), ["$A$", "$A$", "$B$"])


if __name__ == "__main__":
    unittest.main()
