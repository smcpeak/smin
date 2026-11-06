# token_tree_test.py
"""
Unit tests for token_tree.
"""

from __future__ import annotations

import unittest

from smin_token import SMToken
from token_tree import TTNode, TTNodeKind


def sm_token(text: bytes) -> SMToken:
  """Make a token with `text`.  The other attributes are irrelevant here."""
  return SMToken(text, 0, 0, False, False)


def tok(text: bytes) -> TTNode:
  """Make a token node with `text`."""
  return TTNode.make_token(sm_token(text))


def delim(open: bytes, children: list[TTNode], close: bytes) -> TTNode:
  """Make a delimiter group bounded by `open` and `close`."""
  return TTNode.make_group(TTNodeKind.DELIMITER,
                           [tok(open)] + children + [tok(close)])


def sample_tree() -> TTNode:
  """
  Make a tree for:

    f(a, b);
    x;
  """
  return TTNode.make_group(TTNodeKind.ROOT, [
    TTNode.make_group(TTNodeKind.LINE, [
      tok(b"f"),
      delim(b"(", [tok(b"a"), tok(b","), tok(b" b")], b")"),
      tok(b";"),
    ]),
    tok(b"\nx;"),
  ])


class TTNodeTest(unittest.TestCase):
  def test_make_token(self) -> None:
    t = sm_token(b"abc")
    n = TTNode.make_token(t)
    self.assertTrue(n.is_token())
    self.assertFalse(n.is_group())
    self.assertIs(n.token, t)
    self.assertEqual(n.children, [])
    self.assertFalse(n.is_delim_group())

  def test_make_group(self) -> None:
    a = tok(b"a")
    b = tok(b"b")
    n = TTNode.make_group(TTNodeKind.ROOT, [a, b])
    self.assertTrue(n.is_group())
    self.assertFalse(n.is_token())
    self.assertIsNone(n.token)
    self.assertEqual(n.children, [a, b])
    self.assertFalse(n.is_delim_group())

  def test_make_delim_group(self) -> None:
    n = TTNode.make_group(TTNodeKind.DELIMITER, [tok(b"("), tok(b")")])
    self.assertTrue(n.is_group())
    self.assertTrue(n.is_delim_group())

  def test_default_children_not_shared(self) -> None:
    n1 = TTNode(kind=TTNodeKind.ROOT)
    n2 = TTNode(kind=TTNodeKind.ROOT)
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
    self.assertEqual(TTNode.make_group(TTNodeKind.ROOT, []).text(), b"")

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
    n = TTNode.make_group(TTNodeKind.ROOT, [
      TTNode.make_group(TTNodeKind.PARAGRAPH,
        [TTNode.make_group(TTNodeKind.LINE, [tok(b"a"), tok(b"b")])]),
      TTNode.make_group(TTNodeKind.PARAGRAPH,
        [tok(b"c"), TTNode.make_group(TTNodeKind.LINE, [tok(b"d")])]),
    ])
    self.assertEqual(n.first_token().text, b"a")
    self.assertEqual(n.last_token().text, b"d")

  def test_depth(self) -> None:
    self.assertEqual(tok(b"a").depth(), 0)
    self.assertEqual(
      TTNode.make_group(TTNodeKind.ROOT, []).depth(),
      0)
    self.assertEqual(
      TTNode.make_group(TTNodeKind.ROOT, [tok(b"a")]).depth(),
      1)
    # Root -> statement group -> delimiter group -> token.
    self.assertEqual(sample_tree().depth(), 3)

  def test_self_check_valid(self) -> None:
    sample_tree().self_check()
    tok(b"a").self_check()
    TTNode.make_group(TTNodeKind.ROOT, []).self_check()

  def test_self_check_token_with_children(self) -> None:
    n = TTNode(kind     = TTNodeKind.TOKEN,
               token    = sm_token(b"a"),
               children = [tok(b"b")])
    with self.assertRaisesRegex(AssertionError, "token node has children"):
      n.self_check()

  def test_self_check_token_marked_delim_group(self) -> None:
    n = TTNode(TTNodeKind.DELIMITER, token=sm_token(b"a"))
    with self.assertRaisesRegex(AssertionError, "delim group lacks delimiters"):
      n.self_check()

  def test_self_check_delim_group_too_short(self) -> None:
    n = TTNode.make_group(TTNodeKind.DELIMITER, [tok(b"(")])
    with self.assertRaisesRegex(AssertionError, "delim group lacks delimiters"):
      n.self_check()

  def test_self_check_delim_group_opener_not_token(self) -> None:
    n = TTNode.make_group(TTNodeKind.DELIMITER, [
      TTNode.make_group(TTNodeKind.LINE, [tok(b"("), tok(b"a")]),
      tok(b")")
    ])
    with self.assertRaisesRegex(AssertionError, "opener is not a token"):
      n.self_check()

  def test_self_check_delim_group_closer_not_token(self) -> None:
    n = TTNode.make_group(TTNodeKind.DELIMITER, [
      tok(b"("),
      TTNode.make_group(TTNodeKind.LINE, [tok(b"a"), tok(b")")])
    ])
    with self.assertRaisesRegex(AssertionError, "closer is not a token"):
      n.self_check()

  def test_self_check_recurses(self) -> None:
    bad = TTNode(TTNodeKind.DELIMITER, token=sm_token(b"a"))
    n = TTNode.make_group(TTNodeKind.ROOT, [
          tok(b"x"),
          TTNode.make_group(TTNodeKind.LINE, [tok(b"y"), bad])
        ])
    with self.assertRaisesRegex(AssertionError, "delim group lacks delimiters"):
      n.self_check()

  def test_to_debug_string_token(self) -> None:
    self.assertEqual(tok(b"a\n").to_debug_string(), '"a\\n"\n')
    self.assertEqual(tok(b"a").to_debug_string(4), '    "a"\n')

  def test_to_debug_string_tree(self) -> None:
    expect = (
      'ROOT[\n'
      '  LINE[\n'
      '    "f"\n'
      '    DELIMITER[\n'
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
    self.assertEqual(TTNode.make_group(TTNodeKind.ROOT, [])
                       .to_debug_string(2), "  ROOT[\n  ]\n")


if __name__ == "__main__":
  unittest.main()


# EOF
