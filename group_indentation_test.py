# group_indentation_test.py
"""
Unit tests for group_indentation.
"""

from __future__ import annotations

import unittest

from group_delimiters import group_delimiters
from group_indentation import group_indentation
from group_lines import group_lines
from test_util import all_groups, all_nodes, dedent
from token_tree import TTNode
from tokenize_cpp import tokenize_cpp


def delim_group_texts(node: TTNode) -> list[bytes]:
  """Return the text of each delimiter group under `node`, in preorder."""
  return [g.text() for g in all_groups(node) if g.delim_group]


class GroupIndentationTest(unittest.TestCase):
  def check(self, src: str, expect: str) -> TTNode:
    """
    Check that grouping `src` (dedented) by indentation, after the
    earlier phases, yields a tree whose debug string is `expect`
    (dedented).  Return the tree.
    """
    data = dedent(src).encode("utf-8")
    input_tree = group_lines(group_delimiters(tokenize_cpp(data)))
    input_debug = input_tree.to_debug_string()

    tree = group_indentation(input_tree)

    self.assertEqual(tree.to_debug_string(), dedent(expect))
    self.assertEqual(tree.text(), data)
    tree.self_check()

    # The input tree is unchanged, and shares no nodes with the output,
    # but the tokens themselves are shared.
    self.assertEqual(input_tree.to_debug_string(), input_debug)
    input_ids = {id(n) for n in all_nodes(input_tree)}
    self.assertFalse(any(id(n) in input_ids for n in all_nodes(tree)))
    for t1, t2 in zip(input_tree.tokens(), tree.tokens(), strict=True):
      self.assertIs(t1, t2)

    # Phase 4 neither creates nor destroys delimiter groups.
    self.assertFalse(tree.delim_group)
    self.assertEqual(delim_group_texts(tree), delim_group_texts(input_tree))

    return tree

  def test_empty(self) -> None:
    self.check("", """
      [
      ]
      """)

  def test_no_indentation(self) -> None:
    # Every line ends the previous line's group, so nothing changes.
    self.check("""
      a;
      b;
      """, r"""
      [
        [
          "a"
          ";"
        ]
        [
          "\nb"
          ";"
        ]
        "\n"
      ]
      """)

  def test_continuation_line(self) -> None:
    tree = self.check("""
      int x =
        5;
      y;
      """, r"""
      [
        [
          [
            "int"
            " x"
            " ="
          ]
          [
            "\n  5"
            ";"
          ]
        ]
        [
          "\ny"
          ";"
        ]
        "\n"
      ]
      """)
    self.assertFalse(tree.children[0].delim_group)

  def test_nested(self) -> None:
    self.check("""
      a;
        b;
          c;
        d;
      e;
      """, r"""
      [
        [
          [
            "a"
            ";"
          ]
          [
            [
              "\n  b"
              ";"
            ]
            [
              "\n    c"
              ";"
            ]
          ]
          [
            "\n  d"
            ";"
          ]
        ]
        [
          "\ne"
          ";"
        ]
        "\n"
      ]
      """)

  def test_dedent_to_intermediate_level(self) -> None:
    # The "c" line ends the "b" group, but not the "a" group, and begins
    # a group that has nothing else in it.
    self.check("""
      a;
          b;
        c;
      d;
      """, r"""
      [
        [
          [
            "a"
            ";"
          ]
          [
            "\n    b"
            ";"
          ]
          [
            "\n  c"
            ";"
          ]
        ]
        [
          "\nd"
          ";"
        ]
        "\n"
      ]
      """)

  def test_delimiters_excluded(self) -> None:
    # The "{" and "}" are first on their lines, but are not grouped with
    # the lines between them.
    self.check("""
      f()
      {
        a;
          b;
        c;
      }
      """, r"""
      [
        [
          "f"
          [
            "("
            ")"
          ]
        ]
        [
          "\n{"
          [
            [
              "\n  a"
              ";"
            ]
            [
              "\n    b"
              ";"
            ]
          ]
          [
            "\n  c"
            ";"
          ]
          "\n}"
        ]
        "\n"
      ]
      """)

  def test_closer_not_first_on_line(self) -> None:
    # The "2" is not grouped with the closer that follows it.
    self.check("""
      x = [
        1,
        2]
      """, r"""
      [
        [
          "x"
          " ="
          [
            " ["
            [
              "\n  1"
              ","
            ]
            "\n  2"
            "]"
          ]
        ]
        "\n"
      ]
      """)

  def test_node_not_first_on_line_joins_innermost_group(self) -> None:
    # The trailing whitespace token is not first on its line, so it
    # belongs to the innermost open group.  The group starting with "a"
    # would span the whole root, so it is not made.
    self.check("a\n  b ", r"""
      [
        "a"
        [
          "\n  b"
          " "
        ]
      ]
      """)

  def test_line_groups_not_rewrapped(self) -> None:
    # Within a line group from Phase 3, the first node is first on its
    # line, so the whole line would form an indentation group, which
    # would be redundant.
    tree = self.check("a b;", r"""
      [
        [
          "a"
          " b"
          ";"
        ]
      ]
      """)
    line = tree.children[0]
    self.assertEqual(len(line.children), 3)

  def test_delimiter_interior_wrapped(self) -> None:
    # The interior of a delimiter group can become one group, since that
    # is not redundant: it excludes the delimiters.
    self.check("""
      (
        a;
          b;
      )
      """, r"""
      [
        [
          "("
          [
            [
              "\n  a"
              ";"
            ]
            [
              "\n    b"
              ";"
            ]
          ]
          "\n)"
        ]
        "\n"
      ]
      """)

  def test_python_example(self) -> None:
    # Part of example input 3 from the spec.
    self.check("""
      for i, comp in enumerate(sccs):
        for n in comp:
          node_to_scc[n] = i
      """, r"""
      [
        [
          [
            "for"
            " i"
            ","
            " comp"
            " in"
            " enumerate"
            [
              "("
              "sccs"
              ")"
            ]
            ":"
          ]
          [
            [
              "\n  for"
              " n"
              " in"
              " comp"
              ":"
            ]
            [
              "\n    node_to_scc"
              [
                "["
                "n"
                "]"
              ]
              " ="
              " i"
            ]
          ]
        ]
        "\n"
      ]
      """)


if __name__ == "__main__":
  unittest.main()


# EOF
