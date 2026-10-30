# build_tree_test.py
"""
Unit tests for build_tree.
"""

from __future__ import annotations

import unittest

from build_tree import build_tree
from test_util import all_groups, dedent
from token_tree import TTNode
from tokenize_cpp import tokenize_cpp


class BuildTreeTest(unittest.TestCase):
  def check(self, src: str, expect: str) -> TTNode:
    """
    Check that building the tree for `src` (dedented) yields a tree
    whose debug string is `expect` (dedented).  Return the tree.
    """
    data = dedent(src).encode("utf-8")
    tokens = tokenize_cpp(data)

    tree = build_tree(tokens)

    self.assertEqual(tree.to_debug_string(), dedent(expect))
    self.assertEqual(tree.text(), data)
    tree.self_check()
    for t1, t2 in zip(tokens, tree.tokens(), strict=True):
      self.assertIs(t1, t2)
    self.assertFalse(tree.delim_group)

    # Phase 6 is unnecessary because no non-root group has a single
    # child.
    for g in all_groups(tree):
      if g is not tree:
        self.assertGreater(len(g.children), 1)

    return tree

  def test_empty(self) -> None:
    self.check("", """
      [
      ]
      """)

  def test_root_with_one_child(self) -> None:
    # The one place a single-child group can appear is the root, when
    # the input consists of a single delimiter group.
    self.check("()", """
      [
        [
          "("
          ")"
        ]
      ]
      """)

  def test_cpp_hello_world(self) -> None:
    # Example input 1 from the spec.  This matches example output 1,
    # whose quoted strings combine some tokens (as notational
    # convenience).
    self.check(r"""
      #include <iostream>        // std::cout

      int main(int argc, char **argv)
      {
        std::cout << "Hello\n";
        return 0;
      }
      """, r"""
      [
        [
          "#include <iostream>"
          "        // std::cout"
        ]
        [
          [
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
          ]
          [
            "\n{"
            [
              [
                "\n  std"
                "::"
                "cout"
                " <<"
                " \"Hello\\n\""
                ";"
              ]
              [
                "\n  return"
                " 0"
                ";"
              ]
            ]
            "\n}"
          ]
          "\n"
        ]
      ]
      """)

  def test_cpp_if_statements(self) -> None:
    # Example input 2 from the spec.
    self.check(r"""
      bool GetDepsVisitor::isRefactoringDN(DependencyNode dn) const
      {
        // Must be a named declaration.
        if (!isa<clang::NamedDecl>(dn.m_decl)) {
          return false;
        }

        // What is its syntactic parent?
        clang::NamedDecl const *parent =
          getNamedParentDeclOpt_templateAdjustment(dn.m_decl);
        if (!parent) {
          // The parent is the TU.
          return true;
        }

        return true;
      }
      """, r"""
      [
        [
          "bool"
          " GetDepsVisitor"
          "::"
          "isRefactoringDN"
          [
            "("
            "DependencyNode"
            " dn"
            ")"
          ]
          " const"
        ]
        [
          "\n{"
          [
            "\n  // Must be a named declaration."
            [
              "\n  if"
              [
                " ("
                "!"
                "isa"
                "<"
                "clang"
                "::"
                "NamedDecl"
                ">"
                [
                  "("
                  "dn"
                  "."
                  "m_decl"
                  ")"
                ]
                ")"
              ]
              [
                " {"
                [
                  "\n    return"
                  " false"
                  ";"
                ]
                "\n  }"
              ]
            ]
          ]
          [
            "\n\n  // What is its syntactic parent?"
            [
              [
                "\n  clang"
                "::"
                "NamedDecl"
                " const"
                " *"
                "parent"
                " ="
              ]
              [
                "\n    getNamedParentDeclOpt_templateAdjustment"
                [
                  "("
                  "dn"
                  "."
                  "m_decl"
                  ")"
                ]
                ";"
              ]
            ]
            [
              "\n  if"
              [
                " ("
                "!"
                "parent"
                ")"
              ]
              [
                " {"
                [
                  "\n    // The parent is the TU."
                  [
                    "\n    return"
                    " true"
                    ";"
                  ]
                ]
                "\n  }"
              ]
            ]
          ]
          [
            "\n\n  return"
            " true"
            ";"
          ]
          "\n}"
        ]
        "\n"
      ]
      """)

  def test_depth(self) -> None:
    self.assertEqual(build_tree(tokenize_cpp(b"")).depth(), 0)
    self.assertEqual(build_tree(tokenize_cpp(b"a b")).depth(), 1)
    # Root -> delimiter group -> delimiter group -> token.
    self.assertEqual(build_tree(tokenize_cpp(b"f(g(x))")).depth(), 3)


if __name__ == "__main__":
  unittest.main()


# EOF
