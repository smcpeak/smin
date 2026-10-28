# group_lines_test.py
"""
Unit tests for group_lines.
"""

from __future__ import annotations

import unittest

from group_delimiters import group_delimiters
from group_lines import group_lines
from test_util import all_groups, all_nodes, dedent
from token_tree import TTNode
from tokenize_cpp import tokenize_cpp


def delim_group_texts(node: TTNode) -> list[bytes]:
  """Return the text of each delimiter group under `node`, in preorder."""
  return [g.text() for g in all_groups(node) if g.delim_group]


class GroupLinesTest(unittest.TestCase):
  def check(self, src: str, expect: str) -> TTNode:
    """
    Check that grouping the lines of `src` (dedented), after grouping
    its delimiters, yields a tree whose debug string is `expect`
    (dedented).  Return the tree.
    """
    data = dedent(src).encode("utf-8")
    input_tree = group_delimiters(tokenize_cpp(data))
    input_debug = input_tree.to_debug_string()

    tree = group_lines(input_tree)

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

    # Phase 3 neither creates nor destroys delimiter groups.
    self.assertFalse(tree.delim_group)
    self.assertEqual(delim_group_texts(tree), delim_group_texts(input_tree))

    return tree

  def test_empty(self) -> None:
    self.check("", """
      [
      ]
      """)

  def test_one_line(self) -> None:
    # The line would span the whole root, so it is not made into a group.
    self.check("a b;", r"""
      [
        "a"
        " b"
        ";"
      ]
      """)

  def test_one_line_then_newline(self) -> None:
    tree = self.check("a b;\n", r"""
      [
        [
          "a"
          " b"
          ";"
        ]
        "\n"
      ]
      """)
    self.assertFalse(tree.children[0].delim_group)

  def test_several_lines(self) -> None:
    self.check("""
      a;
      b c;
      """, r"""
      [
        [
          "a"
          ";"
        ]
        [
          "\nb"
          " c"
          ";"
        ]
        "\n"
      ]
      """)

  def test_several_statements_on_one_line(self) -> None:
    self.check("a; b;\n", r"""
      [
        [
          "a"
          ";"
          " b"
          ";"
        ]
        "\n"
      ]
      """)

  def test_single_node_line_not_grouped(self) -> None:
    self.check("""
      a
      b c
      """, r"""
      [
        "a"
        [
          "\nb"
          " c"
        ]
        "\n"
      ]
      """)

  def test_trailing_comment(self) -> None:
    self.check("""
      a; // c
      b;
      """, r"""
      [
        [
          "a"
          ";"
          " // c"
        ]
        [
          "\nb"
          ";"
        ]
        "\n"
      ]
      """)

  def test_eof_whitespace_without_newline(self) -> None:
    self.check("a; ", r"""
      [
        [
          "a"
          ";"
        ]
        " "
      ]
      """)

  def test_line_starting_after_multi_line_comment(self) -> None:
    # The " a" is not first on its line, so the line group begins with
    # the comment.
    self.check("""
      /* x
       */ a;
      b;
      """, r"""
      [
        [
          "/* x\n */"
          " a"
          ";"
        ]
        [
          "\nb"
          ";"
        ]
        "\n"
      ]
      """)

  def test_function_same_line_brace(self) -> None:
    # The opening brace is on the header line, so the line group spans
    # the whole definition.
    tree = self.check("""
      void f() {
        x;
      }
      """, r"""
      [
        [
          "void"
          " f"
          [
            "("
            ")"
          ]
          [
            " {"
            [
              "\n  x"
              ";"
            ]
            "\n}"
          ]
        ]
        "\n"
      ]
      """)
    line = tree.children[0]
    self.assertFalse(line.delim_group)
    self.assertTrue(line.children[3].delim_group)
    self.assertFalse(line.children[3].children[1].delim_group)

  def test_function_next_line_brace(self) -> None:
    # The opening brace is on its own line, so the header and body are
    # separate.  The body is both first and last on its line(s), so it is
    # not wrapped in a redundant group.
    self.check("""
      int main()
      {
        return 0;
      }
      """, r"""
      [
        [
          "int"
          " main"
          [
            "("
            ")"
          ]
        ]
        [
          "\n{"
          [
            "\n  return"
            " 0"
            ";"
          ]
          "\n}"
        ]
        "\n"
      ]
      """)

  def test_closer_excluded(self) -> None:
    # The "b" is first on its line, but the only node after it that is
    # last on its line is the closing delimiter, which cannot be grouped.
    self.check("""
      foo(a,
          b);
      """, r"""
      [
        [
          "foo"
          [
            "("
            "a"
            ","
            "\n    b"
            ")"
          ]
          ";"
        ]
        "\n"
      ]
      """)

  def test_opener_excluded(self) -> None:
    # The "{" is first on its line, but cannot be grouped with the ";"
    # that is last on that line.
    self.check("""
      { a;
        b; }
      """, r"""
      [
        [
          "{"
          " a"
          ";"
          "\n  b"
          ";"
          " }"
        ]
        "\n"
      ]
      """)

  def test_unpaired_delimiters_are_ordinary(self) -> None:
    self.check("""
      a (
      b;
      """, r"""
      [
        [
          "a"
          " ("
        ]
        [
          "\nb"
          ";"
        ]
        "\n"
      ]
      """)

  def test_nested_lines(self) -> None:
    self.check("""
      if (x) {
        a = f(
          1);
        b;
      }
      """, r"""
      [
        [
          "if"
          [
            " ("
            "x"
            ")"
          ]
          [
            " {"
            [
              "\n  a"
              " ="
              " f"
              [
                "("
                "\n    1"
                ")"
              ]
              ";"
            ]
            [
              "\n  b"
              ";"
            ]
            "\n}"
          ]
        ]
        "\n"
      ]
      """)


if __name__ == "__main__":
  unittest.main()


# EOF
