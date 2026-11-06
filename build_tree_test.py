# build_tree_test.py
"""
Unit tests for build_tree.
"""

from __future__ import annotations

import os
import sys
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
    self.assertFalse(tree.is_delim_group())

    # Phase 6 is unnecessary because no non-root group has a single
    # child.
    for g in all_groups(tree):
      if g is not tree:
        self.assertGreater(len(g.children), 1)

    return tree

  def test_empty(self) -> None:
    self.check("", """
      ROOT[
      ]
      """)

  def test_root_with_one_child(self) -> None:
    # The one place a single-child group can appear is the root, when
    # the input consists of a single delimiter group.
    self.check("()", """
      ROOT[
        DELIMITER[
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
      ROOT[
        LINE[
          "#include <iostream>"
          "        // std::cout"
        ]
        PARAGRAPH[
          HEAD_BODY[
            LINE[
              "\n\nint"
              " main"
              DELIMITER[
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
            DELIMITER[
              "\n{"
              PARAGRAPH[
                LINE[
                  "\n  std"
                  "::"
                  "cout"
                  " <<"
                  " \"Hello\\n\""
                  ";"
                ]
                LINE[
                  "\n  return"
                  " 0"
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

  def test_cpp_if_statements(self) -> None:
    # Example input 2 from the spec.  Phase 4.5 groups the head, which
    # starts with the first token in the file, with its body.
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
      ROOT[
        HEAD_BODY[
          LINE[
            "bool"
            " GetDepsVisitor"
            "::"
            "isRefactoringDN"
            DELIMITER[
              "("
              "DependencyNode"
              " dn"
              ")"
            ]
            " const"
          ]
          DELIMITER[
            "\n{"
            PARAGRAPH[
              "\n  // Must be a named declaration."
              LINE[
                "\n  if"
                DELIMITER[
                  " ("
                  "!"
                  "isa"
                  "<"
                  "clang"
                  "::"
                  "NamedDecl"
                  ">"
                  DELIMITER[
                    "("
                    "dn"
                    "."
                    "m_decl"
                    ")"
                  ]
                  ")"
                ]
                DELIMITER[
                  " {"
                  LINE[
                    "\n    return"
                    " false"
                    ";"
                  ]
                  "\n  }"
                ]
              ]
            ]
            PARAGRAPH[
              "\n\n  // What is its syntactic parent?"
              INDENTATION[
                LINE[
                  "\n  clang"
                  "::"
                  "NamedDecl"
                  " const"
                  " *"
                  "parent"
                  " ="
                ]
                LINE[
                  "\n    getNamedParentDeclOpt_templateAdjustment"
                  DELIMITER[
                    "("
                    "dn"
                    "."
                    "m_decl"
                    ")"
                  ]
                  ";"
                ]
              ]
              LINE[
                "\n  if"
                DELIMITER[
                  " ("
                  "!"
                  "parent"
                  ")"
                ]
                DELIMITER[
                  " {"
                  PARAGRAPH[
                    "\n    // The parent is the TU."
                    LINE[
                      "\n    return"
                      " true"
                      ";"
                    ]
                  ]
                  "\n  }"
                ]
              ]
            ]
            LINE[
              "\n\n  return"
              " true"
              ";"
            ]
            "\n}"
          ]
        ]
        "\n"
      ]
      """)

  def test_depth(self) -> None:
    self.assertEqual(build_tree(tokenize_cpp(b"")).depth(), 0)
    self.assertEqual(build_tree(tokenize_cpp(b"a b")).depth(), 1)
    # Root -> delimiter group -> delimiter group -> token.
    self.assertEqual(build_tree(tokenize_cpp(b"f(g(x))")).depth(), 3)


def print_tree_for_file(fname: str) -> None:
  """
  Build the token tree for the C++ file `fname`, and print its debug
  string.  This is a debugging aid, not a test.
  """
  with open(fname, "rb") as f:
    data = f.read()
  print(build_tree(tokenize_cpp(data)).to_debug_string(), end="")


if __name__ == "__main__":
  # With a single argument that names a file, print its tree.  Otherwise,
  # run the tests, passing any arguments to unittest (which accepts test
  # names, which are unlikely to also be file names).
  if len(sys.argv) == 2 and os.path.isfile(sys.argv[1]):
    print_tree_for_file(sys.argv[1])
  else:
    unittest.main()


# EOF
