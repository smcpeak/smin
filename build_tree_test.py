# build_tree_test.py
"""
Unit tests for build_tree.
"""

from __future__ import annotations

import textwrap
import unittest

from build_tree import LineInfo, compute_line_info, group_delimiters
from smin_token import SMToken
from token_tree import TTNode
from tokenize_cpp import CPPTokenizer


def dedent(s: str) -> str:
  """Dedent `s` and remove one leading newline, if present."""
  s = textwrap.dedent(s)
  return s[1:] if s.startswith("\n") else s


def all_groups(node: TTNode) -> list[TTNode]:
  """Return all group nodes under (and including) `node`, in preorder."""
  if node.is_token():
    return []
  groups = [node]
  for child in node.children:
    groups.extend(all_groups(child))
  return groups


class ComputeLineInfoTest(unittest.TestCase):
  def info(self, texts: list[bytes]) -> list[tuple[int, bool]]:
    """Return the result of running `compute_line_info` on `texts`."""
    infos = compute_line_info([SMToken(t) for t in texts])
    return [(i.indentation, i.first_on_line) for i in infos]

  def test_empty(self) -> None:
    self.assertEqual(self.info([]), [])

  def test_first_token(self) -> None:
    self.assertEqual(self.info([b"a"]), [(0, True)])
    self.assertEqual(self.info([b"  a"]), [(2, True)])

  def test_same_line(self) -> None:
    self.assertEqual(self.info([b"  a", b" b", b"c"]),
                     [(2, True), (2, False), (2, False)])

  def test_new_lines(self) -> None:
    self.assertEqual(self.info([b"a", b"\n\t b", b" c", b"\n\nd"]),
                     [(0, True), (2, True), (2, False), (0, True)])

  def test_tabs_count_as_one(self) -> None:
    self.assertEqual(self.info([b"\t\ta"]), [(2, True)])

  def test_multi_line_token(self) -> None:
    # A token that begins on the last line of a multi-line token is not
    # first on its line, and has that line's indentation.
    self.assertEqual(self.info([b"  /* a\n    b */", b" c", b"\nd"]),
                     [(2, True), (4, False), (0, True)])

  def test_multi_line_token_ending_with_newline(self) -> None:
    self.assertEqual(self.info([b"#define X \\\n", b"   y"]),
                     [(0, True), (3, True)])

  def test_whitespace_only_token(self) -> None:
    self.assertEqual(self.info([b"a", b"\n  "]), [(0, True), (2, True)])
    self.assertEqual(self.info([b"  a", b"  "]), [(2, True), (2, False)])

  def test_line_info_is_frozen(self) -> None:
    info = LineInfo(1, True)
    with self.assertRaises(AttributeError):
      # The type annotation here suppresses mypy's complaint that the
      # class is frozen.  The point of this test is to confirm that
      # there is run-time enforcement of that fact.
      info.indentation = 2  # type: ignore[misc]


class GroupDelimitersTest(unittest.TestCase):
  def check(self, src: str, expect: str) -> TTNode:
    """
    Check that grouping the delimiters of `src` (dedented) yields a tree
    whose debug string is `expect` (dedented).  Return the tree.
    """
    data = dedent(src).encode("utf-8")
    tokenizer = CPPTokenizer()
    tree = group_delimiters(tokenizer.tokenize(data), tokenizer)

    self.assertEqual(tree.to_debug_string(), dedent(expect))
    self.assertEqual(tree.text(), data)
    tree.self_check()

    # Phase 2 creates only delimiter groups, under a root that is not.
    self.assertFalse(tree.delim_group)
    for group in all_groups(tree)[1:]:
      self.assertTrue(group.delim_group)

    return tree

  def test_empty(self) -> None:
    self.check("", """
      [
      ]
      """)

  def test_no_delimiters(self) -> None:
    self.check("a b;", r"""
      [
        "a"
        " b"
        ";"
      ]
      """)

  def test_simple(self) -> None:
    tree = self.check("f(x);", r"""
      [
        "f"
        [
          "("
          "x"
          ")"
        ]
        ";"
      ]
      """)
    self.assertTrue(tree.children[1].delim_group)

  def test_nested(self) -> None:
    self.check("a[(b)]{}", r"""
      [
        "a"
        [
          "["
          [
            "("
            "b"
            ")"
          ]
          "]"
        ]
        [
          "{"
          "}"
        ]
      ]
      """)

  def test_eof_whitespace(self) -> None:
    self.check("()\n", r"""
      [
        [
          "("
          ")"
        ]
        "\n"
      ]
      """)

  def test_comments_and_strings_are_not_delimiters(self) -> None:
    self.check("""
      f( // )
        ")"
      )
      """, r"""
      [
        "f"
        [
          "("
          " // )"
          "\n  \")\""
          "\n)"
        ]
        "\n"
      ]
      """)

  def test_unpaired_closer_at_top_level(self) -> None:
    tree = self.check("a)", r"""
      [
        "a"
        ")"
      ]
      """)
    self.assertEqual(len(all_groups(tree)), 1)

  def test_unpaired_opener_at_eof(self) -> None:
    self.check("f(a[b", r"""
      [
        "f"
        "("
        "a"
        "["
        "b"
      ]
      """)

  def test_unpaired_closer_inside_group(self) -> None:
    self.check("(a ] b)", r"""
      [
        [
          "("
          "a"
          " ]"
          " b"
          ")"
        ]
      ]
      """)

  def test_mismatch_search_finds_opener(self) -> None:
    # The "}" is not first on its line, and the top of the stack is "(",
    # so the stack is searched for a "{" with the same indentation.
    self.check("{ ( }", r"""
      [
        [
          "{"
          " ("
          " }"
        ]
      ]
      """)

  def test_mismatch_search_requires_same_indentation(self) -> None:
    self.check("""
      {
        ( }
      """, r"""
      [
        "{"
        "\n  ("
        " }"
        "\n"
      ]
      """)

  def test_mismatch_search_requires_same_kind(self) -> None:
    self.check("""
      [
        (
      }
      """, r"""
      [
        "["
        "\n  ("
        "\n}"
        "\n"
      ]
      """)

  def test_mid_line_closer_pairs_with_top(self) -> None:
    # The first "}" is indented more than its opener, but it is not first
    # on its line, so it pairs with the top of the stack anyway.
    self.check("""
      {
        if {
          y; }
      }
      """, r"""
      [
        [
          "{"
          "\n  if"
          [
            " {"
            "\n    y"
            ";"
            " }"
          ]
          "\n}"
        ]
        "\n"
      ]
      """)

  def test_line_first_closer_without_indentation_match(self) -> None:
    # No "(" has the closer's indentation, so it pairs with the top.
    self.check("""
      x = f(
            a
          );
      """, r"""
      [
        "x"
        " ="
        " f"
        [
          "("
          "\n      a"
          "\n    )"
        ]
        ";"
        "\n"
      ]
      """)

  def test_line_first_closer_pops_other_kind(self) -> None:
    self.check("""
      f() {
        g(
      }
      """, r"""
      [
        "f"
        [
          "("
          ")"
        ]
        [
          " {"
          "\n  g"
          "("
          "\n}"
        ]
        "\n"
      ]
      """)

  def test_line_first_closer_pops_same_kind(self) -> None:
    self.check("""
      (
        [
      )
      """, r"""
      [
        [
          "("
          "\n  ["
          "\n)"
        ]
        "\n"
      ]
      """)

  def test_line_first_closer_prefers_indentation(self) -> None:
    # The example from the spec's rationale for the line-first rule.
    tree = self.check("""
      void f() {
      #if A
        if (a) {
      #else
        if (b) {
      #endif
          x();
        }
      }
      """, r"""
      [
        "void"
        " f"
        [
          "("
          ")"
        ]
        [
          " {"
          "\n#if A"
          "\n  if"
          [
            " ("
            "a"
            ")"
          ]
          " {"
          "\n#else"
          "\n  if"
          [
            " ("
            "b"
            ")"
          ]
          [
            " {"
            "\n#endif"
            "\n    x"
            [
              "("
              ")"
            ]
            ";"
            "\n  }"
          ]
          "\n}"
        ]
        "\n"
      ]
      """)

    # The unpaired " {" after "if (a)" is an ordinary token.
    body = tree.children[3]
    self.assertTrue(body.children[4].is_token())
    self.assertEqual(body.children[4].text(), b" {")


  def test_cpp_hello_world(self) -> None:
    """Example input 1, C++ Hello World, from the spec."""

    # Note: This test only exercises Pass 2 (delimiters), so the output
    # here is not the same as what the spec shows the as the final tree.
    self.check(r"""
      #include <iostream>        // std::cout

      int main(int argc, char **argv)
      {
        std::cout << "Hello\n";
        return 0;
      }
      """, r"""
      [
        "#include <iostream>"
        "        // std::cout"
        "\n\nint"
        " main"
        [
          "("
          "int"
          " argc"
          ","
          " char"
          " *"
          "*"
          "argv"
          ")"
        ]
        [
          "\n{"
          "\n  std"
          "::"
          "cout"
          " <<"
          " \"Hello\\n\""
          ";"
          "\n  return"
          " 0"
          ";"
          "\n}"
        ]
        "\n"
      ]
      """)


if __name__ == "__main__":
  unittest.main()


# EOF
