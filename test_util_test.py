# test_util_test.py
"""
Unit tests for test_util.
"""

from __future__ import annotations

import unittest

from smin_token import SMToken
from test_util import all_groups, all_nodes, dedent
from token_tree import TTNode


def tok(text: bytes) -> TTNode:
  """Make a token node with `text`.  The other attributes are irrelevant."""
  return TTNode.make_token(SMToken(text, 0, 0, False, False))


class DedentTest(unittest.TestCase):
  def test_empty(self) -> None:
    self.assertEqual(dedent(""), "")

  def test_no_indentation(self) -> None:
    self.assertEqual(dedent("a\nb\n"), "a\nb\n")

  def test_removes_common_indentation(self) -> None:
    self.assertEqual(dedent("  a\n    b\n  c\n"), "a\n  b\nc\n")

  def test_removes_one_leading_newline(self) -> None:
    self.assertEqual(dedent("\n  a\n"), "a\n")
    self.assertEqual(dedent("\n\n  a\n"), "\na\n")

  def test_trailing_indentation_removed(self) -> None:
    # This is the shape of a typical triple-quoted expected value: the
    # closing quotes are indented, leaving whitespace after the final
    # newline, which must not appear in the result.
    self.assertEqual(dedent("""
      [
      ]
      """), "[\n]\n")

  def test_whitespace_only_lines_ignored(self) -> None:
    # Whitespace-only lines do not limit the common indentation, and
    # become empty.
    self.assertEqual(dedent("    a\n \n    b\n"), "a\n\nb\n")

  def test_backslashes_preserved(self) -> None:
    self.assertEqual(dedent(r"""
      "\n  x"
      """), '"\\n  x"\n')


class TreeTraversalTest(unittest.TestCase):
  def sample_tree(self) -> TTNode:
    """
    Make a tree with this shape:

      [ a [ b [ c ] ] d ]
    """
    return TTNode.make_group([
      tok(b"a"),
      TTNode.make_group([
        tok(b"b"),
        TTNode.make_group([tok(b"c")]),
      ]),
      tok(b"d"),
    ])

  def test_all_nodes_of_token(self) -> None:
    n = tok(b"a")
    nodes = all_nodes(n)
    self.assertEqual(len(nodes), 1)
    self.assertIs(nodes[0], n)

  def test_all_groups_of_token(self) -> None:
    self.assertEqual(all_groups(tok(b"a")), [])

  def test_empty_group(self) -> None:
    g = TTNode.make_group([])
    self.assertEqual([id(n) for n in all_nodes(g)], [id(g)])
    self.assertEqual([id(n) for n in all_groups(g)], [id(g)])

  def test_all_nodes_preorder(self) -> None:
    root = self.sample_tree()
    mid = root.children[1]
    inner = mid.children[1]
    expect = [root, root.children[0], mid, mid.children[0], inner,
              inner.children[0], root.children[2]]
    self.assertEqual([id(n) for n in all_nodes(root)],
                     [id(n) for n in expect])

  def test_all_groups_preorder(self) -> None:
    root = self.sample_tree()
    mid = root.children[1]
    inner = mid.children[1]
    self.assertEqual([id(n) for n in all_groups(root)],
                     [id(root), id(mid), id(inner)])

  def test_subtree(self) -> None:
    root = self.sample_tree()
    mid = root.children[1]
    self.assertEqual([n.text() for n in all_nodes(mid)],
                     [b"bc", b"b", b"c", b"c"])
    self.assertEqual([g.text() for g in all_groups(mid)], [b"bc", b"c"])


if __name__ == "__main__":
  unittest.main()


# EOF
