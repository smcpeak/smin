# group_head_body_test.py
"""
Unit tests for group_head_body.
"""

from __future__ import annotations

import unittest

from group_delimiters import group_delimiters
from group_head_body import group_head_body
from group_indentation import group_indentation
from group_lines import group_lines
from test_util import all_groups, all_nodes, dedent
from token_tree import TTNode
from tokenize_cpp import tokenize_cpp


def delim_group_texts(node: TTNode) -> list[bytes]:
  """Return the text of each delimiter group under `node`, in preorder."""
  return [g.text() for g in all_groups(node) if g.delim_group]


class GroupHeadBodyTest(unittest.TestCase):
  def check_bytes(self, data: bytes, expect: str) -> TTNode:
    """
    Check that grouping heads with bodies in `data`, after the earlier
    phases, yields a tree whose debug string is `expect` (dedented).
    Return the tree.
    """
    input_tree = group_indentation(group_lines(group_delimiters(
      tokenize_cpp(data))))
    input_debug = input_tree.to_debug_string()

    tree = group_head_body(input_tree)

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

    # Phase 4.5 neither creates nor destroys delimiter groups.
    self.assertFalse(tree.delim_group)
    self.assertEqual(delim_group_texts(tree), delim_group_texts(input_tree))

    return tree

  def check(self, src: str, expect: str) -> TTNode:
    """Like `check_bytes`, but with `src` dedented and encoded."""
    return self.check_bytes(dedent(src).encode("utf-8"), expect)

  def test_empty(self) -> None:
    self.check("", """
      [
      ]
      """)

  def test_function(self) -> None:
    self.check("""
      x;
      f()
      {
        a;
      }
      """, r"""
      [
        [
          "x"
          ";"
        ]
        [
          [
            "\nf"
            [
              "("
              ")"
            ]
          ]
          [
            "\n{"
            [
              "\n  a"
              ";"
            ]
            "\n}"
          ]
        ]
        "\n"
      ]
      """)

  def test_inside_delimiters(self) -> None:
    # The body's indentation is that of its opening delimiter.
    self.check("""
      {
        f()
        {
        }
      }
      """, r"""
      [
        [
          "{"
          [
            [
              "\n  f"
              [
                "("
                ")"
              ]
            ]
            [
              "\n  {"
              "\n  }"
            ]
          ]
          "\n}"
        ]
        "\n"
      ]
      """)

  def test_spaces_and_tabs_equivalent(self) -> None:
    # The head is indented with one tab, the body with one space.
    self.check_bytes(b"{\n\tf()\n {\n }\n}\n", r"""
      [
        [
          "{"
          [
            [
              "\n\tf"
              [
                "("
                ")"
              ]
            ]
            [
              "\n {"
              "\n }"
            ]
          ]
          "\n}"
        ]
        "\n"
      ]
      """)

  def test_head_more_indented_than_body(self) -> None:
    self.check("""
      {
          f()
        {
        }
      }
      """, r"""
      [
        [
          "{"
          [
            "\n    f"
            [
              "("
              ")"
            ]
          ]
          [
            "\n  {"
            "\n  }"
          ]
          "\n}"
        ]
        "\n"
      ]
      """)

  def test_first_token_in_file(self) -> None:
    # The first token in the file can begin a head even though there is
    # no newline in its leading whitespace.
    self.check("""
      f()
      {
      }
      """, r"""
      [
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
            "\n}"
          ]
        ]
        "\n"
      ]
      """)

  def test_first_token_in_file_indented(self) -> None:
    # The first token's indentation is all of its leading whitespace.
    self.check_bytes(b"  f()\n  {\n  }\n", r"""
      [
        [
          [
            "  f"
            [
              "("
              ")"
            ]
          ]
          [
            "\n  {"
            "\n  }"
          ]
        ]
        "\n"
      ]
      """)

  def test_first_token_in_file_more_indented_than_body(self) -> None:
    self.check_bytes(b"  f()\n{\n}\n", r"""
      [
        [
          "  f"
          [
            "("
            ")"
          ]
        ]
        [
          "\n{"
          "\n}"
        ]
        "\n"
      ]
      """)

  def test_head_needs_newline(self) -> None:
    # " f" is not first in the file, and has no newline in its leading
    # whitespace, so it cannot begin a head.
    self.check("""
      { f
      {
      }
      }
      """, r"""
      [
        [
          "{"
          " f"
          [
            "\n{"
            "\n}"
          ]
          "\n}"
        ]
        "\n"
      ]
      """)

  def test_blank_line_before_body(self) -> None:
    # The body's opener must be preceded by exactly one newline.
    self.check("""
      x;
      f()

      {
      }
      """, r"""
      [
        [
          "x"
          ";"
        ]
        [
          "\nf"
          [
            "("
            ")"
          ]
        ]
        [
          "\n\n{"
          "\n}"
        ]
        "\n"
      ]
      """)

  def test_crlf_before_body(self) -> None:
    # A CRLF line break before the body's opener is treated like LF.
    self.check_bytes(b"x;\r\nf()\r\n{\r\n}\r\n", r"""
      [
        [
          "x"
          ";"
        ]
        [
          [
            "\r\nf"
            [
              "("
              ")"
            ]
          ]
          [
            "\r\n{"
            "\r\n}"
          ]
        ]
        "\r\n"
      ]
      """)

  def test_crlf_blank_line_before_body(self) -> None:
    self.check_bytes(b"x;\r\nf()\r\n\r\n{\r\n}\r\n", r"""
      [
        [
          "x"
          ";"
        ]
        [
          "\r\nf"
          [
            "("
            ")"
          ]
        ]
        [
          "\r\n\r\n{"
          "\r\n}"
        ]
        "\r\n"
      ]
      """)

  def test_body_on_same_line(self) -> None:
    # "f(" and ")" are not separate siblings; the line group made by
    # Phase 3 already contains both the head and the body.
    self.check("""
      x;
      f() {
      }
      """, r"""
      [
        [
          "x"
          ";"
        ]
        [
          "\nf"
          [
            "("
            ")"
          ]
          [
            " {"
            "\n}"
          ]
        ]
        "\n"
      ]
      """)

  def test_body_must_be_delimiter_group(self) -> None:
    self.check("""
      x;
      f()
      y;
      """, r"""
      [
        [
          "x"
          ";"
        ]
        [
          "\nf"
          [
            "("
            ")"
          ]
        ]
        [
          "\ny"
          ";"
        ]
        "\n"
      ]
      """)

  def test_head_must_not_be_delimiter_group(self) -> None:
    # "()" is first in the file, but is a delimiter group.
    self.check("""
      ()
      {
      }
      """, r"""
      [
        [
          "("
          ")"
        ]
        [
          "\n{"
          "\n}"
        ]
        "\n"
      ]
      """)

  def test_consecutive_bodies(self) -> None:
    # The second body's preceding sibling is the first body, which is a
    # delimiter group, so the second body is not grouped with the pair.
    self.check("""
      x;
      f()
      {
      }
      {
      }
      """, r"""
      [
        [
          "x"
          ";"
        ]
        [
          [
            "\nf"
            [
              "("
              ")"
            ]
          ]
          [
            "\n{"
            "\n}"
          ]
        ]
        [
          "\n{"
          "\n}"
        ]
        "\n"
      ]
      """)


if __name__ == "__main__":
  unittest.main()


# EOF
