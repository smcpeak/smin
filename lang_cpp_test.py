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
    nt = lang.non_trivial_replacement

    # Only the brace group has a replacement, not the parentheses.
    tree = build_tree(tokenizer.tokenize(b"int f(int x) { return x; }\n"))
    replaced = [(n.text(), r) for n in all_nodes(tree.root)
                if (r := nt(n)) is not None]
    self.assertEqual(replaced, [(b" { return x; }", b";")])


  def test_brace_group(self) -> None:
    lang: Language = CPPLanguage()
    tokenizer = lang.make_tokenizer()
    is_bg = lang.is_brace_group

    # Only the brace groups, not the parentheses or brackets, nor the
    # tokens or other groups.
    tree = build_tree(tokenizer.tokenize(
      b"int f(int x) { return x; }\nint a[2] = {1};\n"))
    self.assertEqual([n.text() for n in all_nodes(tree.root) if is_bg(n)],
                     [b" { return x; }", b" {1}"])


if __name__ == "__main__":
  unittest.main()


# EOF
