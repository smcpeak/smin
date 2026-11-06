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
from test_util import check_grouping_phase, dedent
from token_tree import TTNode
from tokenize_cpp import tokenize_cpp


class GroupHeadBodyTest(unittest.TestCase):
  def check_bytes(self, data: bytes, expect: str) -> TTNode:
    """
    Check that grouping heads with bodies in `data`, after the earlier
    phases, yields a tree whose debug string is `expect` (dedented).
    Return the tree.
    """
    input_tree = group_indentation(group_lines(group_delimiters(
      tokenize_cpp(data))))
    return check_grouping_phase(self, data, input_tree, group_head_body,
                                expect)

  def check(self, src: str, expect: str) -> TTNode:
    """Like `check_bytes`, but with `src` dedented and encoded."""
    return self.check_bytes(dedent(src).encode("utf-8"), expect)

  def test_empty(self) -> None:
    self.check("", """
      ROOT[
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
      ROOT[
        LINE[
          "x"
          ";"
        ]
        HEAD_BODY[
          LINE[
            "\nf"
            DELIMITER[
              "("
              ")"
            ]
          ]
          DELIMITER[
            "\n{"
            LINE[
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
      ROOT[
        DELIMITER[
          "{"
          HEAD_BODY[
            LINE[
              "\n  f"
              DELIMITER[
                "("
                ")"
              ]
            ]
            DELIMITER[
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
      ROOT[
        DELIMITER[
          "{"
          HEAD_BODY[
            LINE[
              "\n\tf"
              DELIMITER[
                "("
                ")"
              ]
            ]
            DELIMITER[
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
      ROOT[
        DELIMITER[
          "{"
          LINE[
            "\n    f"
            DELIMITER[
              "("
              ")"
            ]
          ]
          DELIMITER[
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
      ROOT[
        HEAD_BODY[
          LINE[
            "f"
            DELIMITER[
              "("
              ")"
            ]
          ]
          DELIMITER[
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
      ROOT[
        HEAD_BODY[
          LINE[
            "  f"
            DELIMITER[
              "("
              ")"
            ]
          ]
          DELIMITER[
            "\n  {"
            "\n  }"
          ]
        ]
        "\n"
      ]
      """)

  def test_first_token_in_file_more_indented_than_body(self) -> None:
    self.check_bytes(b"  f()\n{\n}\n", r"""
      ROOT[
        LINE[
          "  f"
          DELIMITER[
            "("
            ")"
          ]
        ]
        DELIMITER[
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
      ROOT[
        DELIMITER[
          "{"
          " f"
          DELIMITER[
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
      ROOT[
        LINE[
          "x"
          ";"
        ]
        LINE[
          "\nf"
          DELIMITER[
            "("
            ")"
          ]
        ]
        DELIMITER[
          "\n\n{"
          "\n}"
        ]
        "\n"
      ]
      """)

  def test_crlf_before_body(self) -> None:
    # A CRLF line break before the body's opener is treated like LF.
    self.check_bytes(b"x;\r\nf()\r\n{\r\n}\r\n", r"""
      ROOT[
        LINE[
          "x"
          ";"
        ]
        HEAD_BODY[
          LINE[
            "\r\nf"
            DELIMITER[
              "("
              ")"
            ]
          ]
          DELIMITER[
            "\r\n{"
            "\r\n}"
          ]
        ]
        "\r\n"
      ]
      """)

  def test_crlf_blank_line_before_body(self) -> None:
    self.check_bytes(b"x;\r\nf()\r\n\r\n{\r\n}\r\n", r"""
      ROOT[
        LINE[
          "x"
          ";"
        ]
        LINE[
          "\r\nf"
          DELIMITER[
            "("
            ")"
          ]
        ]
        DELIMITER[
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
      ROOT[
        LINE[
          "x"
          ";"
        ]
        LINE[
          "\nf"
          DELIMITER[
            "("
            ")"
          ]
          DELIMITER[
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
      ROOT[
        LINE[
          "x"
          ";"
        ]
        LINE[
          "\nf"
          DELIMITER[
            "("
            ")"
          ]
        ]
        LINE[
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
      ROOT[
        DELIMITER[
          "("
          ")"
        ]
        DELIMITER[
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
      ROOT[
        LINE[
          "x"
          ";"
        ]
        HEAD_BODY[
          LINE[
            "\nf"
            DELIMITER[
              "("
              ")"
            ]
          ]
          DELIMITER[
            "\n{"
            "\n}"
          ]
        ]
        DELIMITER[
          "\n{"
          "\n}"
        ]
        "\n"
      ]
      """)


if __name__ == "__main__":
  unittest.main()


# EOF
