# lang_cpp_test.py
"""
Unit tests for lang_cpp.
"""

from __future__ import annotations

import unittest

from build_tree import build_tree
from lang_cpp import CPPLanguage
from language import Language
from test_util import all_nodes


class CPPLanguageTest(unittest.TestCase):
  def test_tokenizer(self) -> None:
    lang: Language = CPPLanguage()
    tokens = lang.make_tokenizer().tokenize(b"int x;")
    self.assertEqual([t.text for t in tokens], [b"int", b" x", b";"])

  def test_non_trivial_replacement(self) -> None:
    lang: Language = CPPLanguage()
    tokenizer = lang.make_tokenizer()
    nt = lang.get_non_trivial_replacement_func()

    # Only the brace group has a replacement, not the parentheses.
    tree = build_tree(tokenizer.tokenize(b"int f(int x) { return x; }\n"))
    replaced = [(n.text(), r) for n in all_nodes(tree)
                if (r := nt(n)) is not None]
    self.assertEqual(replaced, [(b" { return x; }", b";")])


if __name__ == "__main__":
  unittest.main()


# EOF
