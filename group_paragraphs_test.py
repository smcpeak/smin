# group_paragraphs_test.py
"""
Unit tests for group_paragraphs.
"""

from __future__ import annotations

import unittest

from group_delimiters import group_delimiters
from group_head_body import group_head_body
from group_indentation import group_indentation
from group_lines import group_lines
from group_paragraphs import group_paragraphs
from test_util import all_groups, all_nodes, dedent
from token_tree import TTNode
from tokenize_cpp import tokenize_cpp


# TODO: This function is duplicated in multiple tests.
def delim_group_texts(node: TTNode) -> list[bytes]:
  """Return the text of each delimiter group under `node`, in preorder."""
  return [g.text() for g in all_groups(node) if g.is_delim_group()]


class GroupParagraphsTest(unittest.TestCase):
  def check_bytes(self, data: bytes, expect: str,
                  skip_toplevel: bool = False) -> TTNode:
    """
    Check that grouping `data` into paragraphs, after the earlier
    phases, and passing `skip_toplevel`, yields a tree whose debug
    string is `expect` (dedented).  Return the tree.
    """
    input_tree = group_head_body(group_indentation(group_lines(
      group_delimiters(tokenize_cpp(data)))))
    input_debug = input_tree.to_debug_string()

    tree = group_paragraphs(input_tree, skip_toplevel=skip_toplevel)

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

    # Phase 5 neither creates nor destroys delimiter groups.
    self.assertFalse(tree.is_delim_group())
    self.assertEqual(delim_group_texts(tree), delim_group_texts(input_tree))

    return tree

  def check(self, src: str, expect: str,
            skip_toplevel: bool = False) -> TTNode:
    """Like `check_bytes`, but with `src` dedented and encoded."""
    return self.check_bytes(dedent(src).encode("utf-8"), expect,
                            skip_toplevel)

  def test_empty(self) -> None:
    self.check("", """
      ROOT[
      ]
      """)

  def test_one_paragraph(self) -> None:
    # The paragraph would span the whole root, so it is not made into a
    # group.  The final newline is first on its line, so it belongs to
    # the paragraph.
    self.check("""
      a;
      b;
      """, r"""
      ROOT[
        LINE[
          "a"
          ";"
        ]
        LINE[
          "\nb"
          ";"
        ]
        "\n"
      ]
      """)

  def test_two_paragraphs(self) -> None:
    self.check("""
      a;
      b;

      c;
      d;
      """, r"""
      ROOT[
        PARAGRAPH[
          LINE[
            "a"
            ";"
          ]
          LINE[
            "\nb"
            ";"
          ]
        ]
        PARAGRAPH[
          LINE[
            "\n\nc"
            ";"
          ]
          LINE[
            "\nd"
            ";"
          ]
          "\n"
        ]
      ]
      """)

  def test_single_line_paragraph_not_grouped(self) -> None:
    self.check("""
      a;

      b;
      c;
      """, r"""
      ROOT[
        LINE[
          "a"
          ";"
        ]
        PARAGRAPH[
          LINE[
            "\n\nb"
            ";"
          ]
          LINE[
            "\nc"
            ";"
          ]
          "\n"
        ]
      ]
      """)

  def test_indentation_change_ends_paragraph(self) -> None:
    # Phase 4 does not group "a" and "b", since they are at the same
    # indentation, nor either of them with "c", which is less indented.
    self.check("""
        a;
        b;
      c;
      d;
      """, r"""
      ROOT[
        PARAGRAPH[
          LINE[
            "  a"
            ";"
          ]
          LINE[
            "\n  b"
            ";"
          ]
        ]
        PARAGRAPH[
          LINE[
            "\nc"
            ";"
          ]
          LINE[
            "\nd"
            ";"
          ]
          "\n"
        ]
      ]
      """)

  def test_blank_line_with_whitespace(self) -> None:
    # A line containing only spaces and tabs is blank.
    self.check_bytes(b"a;\n  \t\nb;\nc;\n", r"""
      ROOT[
        LINE[
          "a"
          ";"
        ]
        PARAGRAPH[
          LINE[
            "\n  \t\nb"
            ";"
          ]
          LINE[
            "\nc"
            ";"
          ]
          "\n"
        ]
      ]
      """)

  def test_crlf_blank_line(self) -> None:
    self.check_bytes(b"a;\r\n\r\nb;\r\nc;\r\n", r"""
      ROOT[
        LINE[
          "a"
          ";"
        ]
        PARAGRAPH[
          LINE[
            "\r\n\r\nb"
            ";"
          ]
          LINE[
            "\r\nc"
            ";"
          ]
          "\r\n"
        ]
      ]
      """)

  def test_blank_line_inside_group_does_not_end_paragraph(self) -> None:
    # The blank line before ")" is inside the "a" line group, so that
    # group and "b" form a paragraph.
    self.check("""
      x;

      a(

      );
      b;
      """, r"""
      ROOT[
        LINE[
          "x"
          ";"
        ]
        PARAGRAPH[
          LINE[
            "\n\na"
            DELIMITER[
              "("
              "\n\n)"
            ]
            ";"
          ]
          LINE[
            "\nb"
            ";"
          ]
          "\n"
        ]
      ]
      """)

  def test_trailing_blank_line(self) -> None:
    # The whitespace at EOF follows a blank line, so it is not part of
    # the paragraph.
    self.check_bytes(b"a;\nb;\n\n", r"""
      ROOT[
        PARAGRAPH[
          LINE[
            "a"
            ";"
          ]
          LINE[
            "\nb"
            ";"
          ]
        ]
        "\n\n"
      ]
      """)

  def test_comments(self) -> None:
    self.check("""
      a;
      // c

      // d
      b;
      """, r"""
      ROOT[
        PARAGRAPH[
          LINE[
            "a"
            ";"
          ]
          "\n// c"
        ]
        PARAGRAPH[
          "\n\n// d"
          LINE[
            "\nb"
            ";"
          ]
          "\n"
        ]
      ]
      """)

  def test_node_not_first_on_line_excluded(self) -> None:
    # Within the braces, " a" and ";" are not first on their line, so
    # they are not part of the paragraph formed by the "b" and "c" lines.
    #
    # The group containing "c" is INDENTATION rather than LINE because,
    # after the delimiter pass, the "}" is above the "c" and ";",
    # neither of which are last on their line, so the lines pass does
    # nothing.  The indentation pass then groups them because there is
    # no intervening token with equal or lower indentation level.
    self.check("""
      { a;
        b;
        c; }
      """, r"""
      ROOT[
        DELIMITER[
          "{"
          " a"
          ";"
          PARAGRAPH[
            LINE[
              "\n  b"
              ";"
            ]
            INDENTATION[
              "\n  c"
              ";"
            ]
          ]
          " }"
        ]
        "\n"
      ]
      """)

  def test_delimiters_excluded(self) -> None:
    # Phase 4.5 groups the header with the brace group, and that pair
    # joins the final newline's paragraph.  The "{" and "}" tokens
    # themselves are not grouped with the lines between them, whose
    # paragraph is therefore made into a group even though it is the
    # entire interior.
    self.check("""
      x;

      f()
      {
        a;
        b;
      }
      """, r"""
      ROOT[
        LINE[
          "x"
          ";"
        ]
        PARAGRAPH[
          HEAD_BODY[
            LINE[
              "\n\nf"
              DELIMITER[
                "("
                ")"
              ]
            ]
            DELIMITER[
              "\n{"
              PARAGRAPH[
                LINE[
                  "\n  a"
                  ";"
                ]
                LINE[
                  "\n  b"
                  ";"
                ]
              ]
              "\n}"
            ]
          ]
          "\n"
        ]
      ]
      """)

  def test_skip_toplevel(self) -> None:
    # Same input as `test_delimiters_excluded`, but the root's children
    # are not grouped into paragraphs.  The lines inside the braces
    # still are.  (The header and brace group are grouped by Phase 4.5.)
    self.check("""
      x;

      f()
      {
        a;
        b;
      }
      """, r"""
      ROOT[
        LINE[
          "x"
          ";"
        ]
        HEAD_BODY[
          LINE[
            "\n\nf"
            DELIMITER[
              "("
              ")"
            ]
          ]
          DELIMITER[
            "\n{"
            PARAGRAPH[
              LINE[
                "\n  a"
                ";"
              ]
              LINE[
                "\n  b"
                ";"
              ]
            ]
            "\n}"
          ]
        ]
        "\n"
      ]
      """, skip_toplevel=True)

  def test_skip_toplevel_empty(self) -> None:
    self.check("", """
      ROOT[
      ]
      """, skip_toplevel=True)


if __name__ == "__main__":
  unittest.main()


# EOF
