# token_tree_test.py
"""
Unit tests for token_tree.
"""

from __future__ import annotations

import unittest

from smin_token import SMToken
from token_tree import TTNode


def tok(text: bytes) -> TTNode:
  """Make a token node with `text`."""
  return TTNode.make_token(SMToken(text))


def delim(open: bytes, children: list[TTNode], close: bytes) -> TTNode:
  """Make a delimiter group bounded by `open` and `close`."""
  return TTNode.make_group([tok(open)] + children + [tok(close)], True)


def sample_tree() -> TTNode:
  """
  Make a tree for:

    f(a, b);
    x;
  """
  return TTNode.make_group([
    TTNode.make_group([
      tok(b"f"),
      delim(b"(", [tok(b"a"), tok(b","), tok(b" b")], b")"),
      tok(b";"),
    ]),
    tok(b"\nx;"),
  ])


class TTNodeTest(unittest.TestCase):
  def test_make_token(self) -> None:
    t = SMToken(b"abc")
    n = TTNode.make_token(t)
    self.assertTrue(n.is_token())
    self.assertFalse(n.is_group())
    self.assertIs(n.token, t)
    self.assertEqual(n.children, [])
    self.assertFalse(n.delim_group)

  def test_make_group(self) -> None:
    a = tok(b"a")
    b = tok(b"b")
    n = TTNode.make_group([a, b])
    self.assertTrue(n.is_group())
    self.assertFalse(n.is_token())
    self.assertIsNone(n.token)
    self.assertEqual(n.children, [a, b])
    self.assertFalse(n.delim_group)

  def test_make_delim_group(self) -> None:
    n = TTNode.make_group([tok(b"("), tok(b")")], delim_group=True)
    self.assertTrue(n.is_group())
    self.assertTrue(n.delim_group)

  def test_default_children_not_shared(self) -> None:
    n1 = TTNode()
    n2 = TTNode()
    n1.children.append(tok(b"a"))
    self.assertEqual(n2.children, [])

  def test_tokens_of_token(self) -> None:
    n = tok(b"a")
    self.assertEqual(list(n.tokens()), [n.token])

  def test_tokens_in_order(self) -> None:
    texts = [t.text for t in sample_tree().tokens()]
    self.assertEqual(
      texts, [b"f", b"(", b"a", b",", b" b", b")", b";", b"\nx;"])

  def test_text(self) -> None:
    self.assertEqual(sample_tree().text(), b"f(a, b);\nx;")
    self.assertEqual(tok(b"abc").text(), b"abc")
    self.assertEqual(TTNode.make_group([]).text(), b"")

  def test_first_and_last_token(self) -> None:
    tree = sample_tree()
    self.assertEqual(tree.first_token().text, b"f")
    self.assertEqual(tree.last_token().text, b"\nx;")

    paren = tree.children[0].children[1]
    self.assertEqual(paren.first_token().text, b"(")
    self.assertEqual(paren.last_token().text, b")")

    n = tok(b"a")
    self.assertIs(n.first_token(), n.token)
    self.assertIs(n.last_token(), n.token)

  def test_first_and_last_token_deep(self) -> None:
    n = TTNode.make_group([
      TTNode.make_group([TTNode.make_group([tok(b"a"), tok(b"b")])]),
      TTNode.make_group([tok(b"c"), TTNode.make_group([tok(b"d")])]),
    ])
    self.assertEqual(n.first_token().text, b"a")
    self.assertEqual(n.last_token().text, b"d")

  def test_self_check_valid(self) -> None:
    sample_tree().self_check()
    tok(b"a").self_check()
    TTNode.make_group([]).self_check()

  def test_self_check_token_with_children(self) -> None:
    n = TTNode(token=SMToken(b"a"), children=[tok(b"b")])
    with self.assertRaises(AssertionError):
      n.self_check()

  def test_self_check_token_marked_delim_group(self) -> None:
    n = TTNode(token=SMToken(b"a"), delim_group=True)
    with self.assertRaises(AssertionError):
      n.self_check()

  def test_self_check_delim_group_too_short(self) -> None:
    n = TTNode.make_group([tok(b"(")], delim_group=True)
    with self.assertRaises(AssertionError):
      n.self_check()

  def test_self_check_delim_group_opener_not_token(self) -> None:
    n = TTNode.make_group(
      [TTNode.make_group([tok(b"("), tok(b"a")]), tok(b")")],
      delim_group=True)
    with self.assertRaises(AssertionError):
      n.self_check()

  def test_self_check_delim_group_closer_not_token(self) -> None:
    n = TTNode.make_group(
      [tok(b"("), TTNode.make_group([tok(b"a"), tok(b")")])],
      delim_group=True)
    with self.assertRaises(AssertionError):
      n.self_check()

  def test_self_check_recurses(self) -> None:
    bad = TTNode(token=SMToken(b"a"), delim_group=True)
    n = TTNode.make_group([tok(b"x"), TTNode.make_group([tok(b"y"), bad])])
    with self.assertRaises(AssertionError):
      n.self_check()

  def test_to_debug_string_token(self) -> None:
    self.assertEqual(tok(b"a\n").to_debug_string(), '"a\\n"\n')
    self.assertEqual(tok(b"a").to_debug_string(4), '    "a"\n')

  def test_to_debug_string_tree(self) -> None:
    expect = (
      '[\n'
      '  [\n'
      '    "f"\n'
      '    [\n'
      '      "("\n'
      '      "a"\n'
      '      ","\n'
      '      " b"\n'
      '      ")"\n'
      '    ]\n'
      '    ";"\n'
      '  ]\n'
      '  "\\nx;"\n'
      ']\n'
    )
    self.assertEqual(sample_tree().to_debug_string(), expect)

  def test_to_debug_string_empty_group(self) -> None:
    self.assertEqual(TTNode.make_group([]).to_debug_string(2), "  [\n  ]\n")


if __name__ == "__main__":
  unittest.main()


# EOF
