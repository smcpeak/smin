# ma_ma3_test.py
"""
Unit tests for ma_ma3 (Minimization Algorithm 3).
"""

from __future__ import annotations

import unittest
from collections.abc import Callable

from build_tree import BuildTreeOptions, build_tree
from lang_cpp import CPPLanguage
from language import Language
from ma_ma3 import BGCTNode, MA3Minimizer, MA3MinimizerSelector
from min_alg_kind import MinimizerAlgorithmKind
from minimizer import Minimizer
from minimizer_test import (
  ACCEPT,
  Recorder,
  ReportCheckingTestCase,
  TEST_LANGUAGE,
)
from start_report import TestStartReport
from test_util import dedent_enc
from tokenize_cpp import tokenize_cpp


# The example input in the spec's BGCT section.
SPEC_EXAMPLE = dedent_enc("""
  int foo()
  {
    return 0;
  }

  int bar()
  {
    while (1) {
      g();
      h();

      if (1) {
        j();
      }
    }
    return 1;
  }
  """)


def balanced(d: bytes) -> bool:
  """True if `d` has as many "{" as "}"."""
  return d.count(b"{") == d.count(b"}")


def label(n: BGCTNode) -> bytes:
  """The first line of the text of `n`, without surrounding whitespace."""
  return n.tt.text().strip().split(b"\n")[0]


def outline(n: BGCTNode) -> list[tuple[int, bytes]]:
  """
  Return (level, label) for `n` and its descendants, in preorder,
  excluding the root.
  """
  ret: list[tuple[int, bytes]] = []
  for c in n.all_children:
    ret.append((c.level, label(c)))
    ret += outline(c)
  return ret


class MA3Test(ReportCheckingTestCase):
  """Tests of Minimization Algorithm 3."""

  # F is the root necessity fraction, which can decrease, and the
  # number of fields depends on the recursion depth.
  CHECK_FRACTION_MONOTONIC = False
  CHECK_FIXED_COLUMNS = False

  def check_granularity(self, r: TestStartReport, m: Minimizer) -> None:
    # The granularity is a number of nodes.
    self.assertEqual(r.granularity, int(r.granularity))
    self.assertGreaterEqual(r.granularity, 1)

  def make(
    self,
    rec: Recorder,
    src: bytes,
    language: Language = TEST_LANGUAGE,
    max_passes: int | None = None,
    **params: int,
  ) -> MA3Minimizer:
    """
    Make an MA3 minimizer for `src` reporting to `rec`, with paragraph
    grouping disabled, and selector parameters `params`.
    """
    tree = build_tree(tokenize_cpp(src),
                      BuildTreeOptions(use_paragraphs=False))
    m = rec.mk_minimizer(tree, rec.min_opts(
      language   = language,
      max_passes = max_passes,
      selector   = MA3MinimizerSelector(**params)))
    assert isinstance(m, MA3Minimizer)
    return m

  def run_ma3(
    self,
    src: bytes,
    accept: Callable[[bytes], bool],
    language: Language = TEST_LANGUAGE,
    max_passes: int | None = None,
    **params: int,
  ) -> tuple[Recorder, MA3Minimizer]:
    """
    Run MA3 on `src` with acceptance predicate `accept`, check the
    reports, and return the recorder and minimizer.
    """
    rec = Recorder(accept)
    m = self.make(rec, src, language, max_passes, **params)
    self.assertEqual(m.run_minimizer(), ACCEPT)
    self.assertTrue(accept(m.get_minimized_test_input()))
    self.check_reports(rec, m)

    # The MA3 report contents are deliberately not checked, but
    # rendering them should work.
    for r in rec.starts:
      self.assertIsNotNone(r.ma3_data)
      self.assertTrue(r.to_console_string().startswith("N="))

    # Every recursive call has finished.
    self.assertEqual(m.cni_stack, [])
    return rec, m

  # ---- BGCT ----
  def test_selector(self) -> None:
    s = MA3MinimizerSelector()
    self.assertEqual(s.alg_kind(), MinimizerAlgorithmKind.MA3)
    self.assertEqual(s.necessity_increment, 10)
    self.assertEqual(s.max_exploration_depth, 4)

  def test_bgct_spec_example(self) -> None:
    # This is the BGCT shown in the spec.
    m = self.make(Recorder(lambda d: True), SPEC_EXAMPLE, CPPLanguage())
    self.assertEqual(m.bgct_root.level, 0)
    self.assertIs(m.bgct_root.tt, m.tree.root)
    self.assertEqual(outline(m.bgct_root), [
      (1, b"int foo()"),
      (2, b"return 0;"),
      (1, b"int bar()"),
      (2, b"while (1) {"),
      (3, b"g();"),
      (3, b"h();"),
      (3, b"if (1) {"),
      (4, b"j();"),
      (2, b"return 1;"),
    ])

    # `bgct_nodes` has all of them, in preorder.
    self.assertEqual(
      [(n.level, label(n)) for n in m.bgct_nodes[1:]],
      outline(m.bgct_root))

  def test_bgct_skips_delimiters_and_other_groups(self) -> None:
    # Within the first line, only the contents of brace groups are BGCT
    # nodes, including those inside parentheses, but not the braces
    # themselves.  A nested brace group is a child of its enclosing one.
    src = b"x = f({1}, {2}) { {4} } {3};\ny;\n"
    m = self.make(Recorder(lambda d: True), src, CPPLanguage())
    self.assertEqual(outline(m.bgct_root), [
      (1, b"x = f({1}, {2}) { {4} } {3};"),
      (2, b"1"),
      (2, b"2"),
      (2, b"{4}"),
      (3, b"4"),
      (2, b"3"),
      (1, b"y;"),
    ])

  def test_children_and_necessary(self) -> None:
    m = self.make(Recorder(lambda d: True), b"a;\nb;\nc;\n")
    root = m.bgct_root
    a, b, c = root.all_children
    self.assertEqual(m.children(root), [a, b, c])
    self.assertEqual(m.necessary(root), [])

    # `necessary` is a suffix of the live children.
    root.num_necessary = 1
    self.assertEqual(m.necessary(root), [c])

    # Replaced nodes are not live.
    m.cur_replacement[id(b.tt)] = b""
    self.assertEqual(m.children(root), [a, c])
    root.num_necessary = 2
    self.assertEqual(m.necessary(root), [a, c])

  def test_children_with_replaced_ancestor(self) -> None:
    # Replacing the brace group, which is not a BGCT node, kills its
    # contents, which are BGCT children of the line.
    m = self.make(Recorder(lambda d: True), b"f() { x; y; }\nz;\n",
                  CPPLanguage())
    line = m.bgct_root.all_children[0]
    self.assertEqual([label(c) for c in m.children(line)],
                     [b"x", b";", b"y", b";"])
    rcpbg = m.rcpbg(line)
    assert rcpbg is not None
    self.assertEqual(rcpbg.text(), b" { x; y; }")
    m.cur_replacement[id(rcpbg)] = b";"
    self.assertEqual(m.children(line), [])
    self.assertIsNone(m.rcpbg(line))

  def test_rcpbg(self) -> None:
    m = self.make(Recorder(lambda d: True), SPEC_EXAMPLE, CPPLanguage())
    root = m.bgct_root
    foo, bar = root.all_children
    while_node, return1 = bar.all_children

    # The root has none, by definition.
    self.assertIsNone(m.rcpbg(root))

    # Neither does a node without children.
    self.assertIsNone(m.rcpbg(return1))

    # Otherwise, it is the brace group enclosing the children.
    def rcpbg_text(n: BGCTNode) -> bytes:
      bg = m.rcpbg(n)
      assert bg is not None
      self.assertTrue(CPPLanguage().is_brace_group(bg))
      return bg.text()
    self.assertEqual(rcpbg_text(foo), b"\n{\n  return 0;\n}")
    self.assertTrue(rcpbg_text(bar).startswith(b"\n{\n  while (1) {"))
    self.assertTrue(rcpbg_text(bar).endswith(b"\n  return 1;\n}"))
    self.assertTrue(rcpbg_text(while_node).startswith(b" {\n    g();"))

  def test_rcpbg_of_brace_group(self) -> None:
    # A brace group that is a BGCT node is its own RCPBG.
    m = self.make(Recorder(lambda d: True), b"{ { x; } }\n", CPPLanguage())
    outer = m.bgct_root.all_children[0]
    inner = outer.all_children[0]
    self.assertIs(m.rcpbg(inner), inner.tt)

  # ---- Number of passes ----
  def test_num_passes(self) -> None:
    rec = Recorder(lambda d: True)

    # The root has 25 children.
    src = b"".join(b"x%d;\n" % i for i in range(25))
    self.assertEqual(self.make(rec, src)._total_num_passes(), 3)
    self.assertEqual(
      self.make(rec, src, necessity_increment=5)._total_num_passes(), 5)
    self.assertEqual(
      self.make(rec, src, max_passes=2)._total_num_passes(), 2)

    # A node below the root with many children counts, unless it is at
    # or below MAX_EXPLORATION_DEPTH.
    src = b"void f()\n{\n" + src + b"}\n"
    m = self.make(rec, src, CPPLanguage())
    self.assertEqual(m._total_num_passes(), 3)
    m = self.make(rec, src, CPPLanguage(), max_exploration_depth=1)
    self.assertEqual(m._total_num_passes(), 1)

    # The minimum is 1.
    self.assertEqual(self.make(rec, b"")._total_num_passes(), 1)

  # ---- Minimization ----
  def test_empty_input(self) -> None:
    rec, m = self.run_ma3(b"", lambda d: True)
    self.assertEqual(m.get_minimized_test_input(), b"")
    self.assertEqual(rec.starts, [])

  def test_accept_everything(self) -> None:
    # The root's children are the three tokens.  Removing the last is
    # accepted, so G doubles to cover the remaining two.
    rec, m = self.run_ma3(b"a b c", lambda d: True)
    self.assertEqual(m.get_minimized_test_input(), b"")
    self.assertEqual(rec.tested, [b"a b", b""])
    self.assertEqual([r.granularity for r in rec.starts], [1, 2])

  def test_keep_one_line(self) -> None:
    # The lines are the root's children.  They have no BGCT children,
    # so the "keep" line cannot be reduced.
    rec, m = self.run_ma3(b"int a;\nint keep;\nint b;\n",
                          lambda d: b"keep" in d)
    self.assertEqual(m.get_minimized_test_input(), b"\nint keep;\n")
    self.assertEqual(rec.tested, [
      # Removing the last line is accepted, so G doubles to 2, but
      # removing both remaining lines is rejected.
      b"int a;\nint keep;\n",
      b"\n",

      # With G=1, the "keep" line is necessary, and the other is not.
      b"int a;\n",
      b"\nint keep;\n",
    ])
    self.assertEqual([r.granularity for r in rec.starts], [1, 2, 1, 1])
    self.assertEqual({r.pass_num for r in rec.starts}, {1})

  def test_rcpbg_replacement(self) -> None:
    # Removing the function is rejected, and it has no non-trivial
    # replacement of its own, but replacing its body is accepted.  The
    # function is then necessary, and the line before it is tried.
    rec, m = self.run_ma3(b"int keep;\nvoid f()\n{\n  x;\n}\n",
                          lambda d: b"f()" in d and balanced(d),
                          CPPLanguage())
    self.assertEqual(m.get_minimized_test_input(), b"\nvoid f()\n;\n")
    self.assertEqual(rec.tested, [
      b"int keep;\n",
      b"int keep;\nvoid f()\n;\n",
      b"\nvoid f()\n;\n",
    ])
    self.assertEqual(m.bgct_root.num_necessary, 1)

    # The function's children were replaced along with the body, so a
    # deeper exploration found nothing to try.
    self.assertEqual(m.children(m.bgct_root.all_children[1]), [])

  def test_non_trivial_replacement(self) -> None:
    # A brace group that is itself a BGCT node is replaced with ";" once
    # removing it is rejected.  Its RCPBG is itself, so that is not
    # tried again.
    rec, m = self.run_ma3(b"{ x; }\nkeep;\n",
                          lambda d: b"keep" in d and b";\n" in d,
                          CPPLanguage())
    self.assertEqual(rec.tested[:2], [b"{ x; }\n", b"\nkeep;\n"])
    self.assertEqual(m.get_minimized_test_input(), b"\nkeep;\n")

  def test_necessity_limit_adds_passes(self) -> None:
    # With NECESSITY_INCREMENT 1, the first pass stops after finding the
    # "c" line necessary.  The second, with a limit of 2, retries it (a
    # memo hit), then removes "b", and finds "a" necessary.  That pass
    # exhausts the children, so it is the last.
    rec, m = self.run_ma3(b"a;\nb;\nc;\n",
                          lambda d: b"a" in d and b"c" in d,
                          necessity_increment=1)
    self.assertEqual(m._total_num_passes(), 3)
    self.assertEqual(m.get_minimized_test_input(), b"a;\nc;\n")
    self.assertEqual(rec.tested, [b"a;\nb;\n", b"a;\nc;\n", b"\nc;\n"])
    self.assertEqual([r.pass_num for r in rec.starts], [1, 2, 2, 2])
    self.assertEqual([memo for _, memo in rec.finishes],
                     [False, True, False, False])
    self.assertEqual(m.max_necessity, 2)

  def test_max_passes(self) -> None:
    # Like `test_necessity_limit_adds_passes`, but stopping after the
    # first pass.
    rec, m = self.run_ma3(b"a;\nb;\nc;\n",
                          lambda d: b"a" in d and b"c" in d,
                          max_passes=1, necessity_increment=1)
    self.assertEqual(m._total_num_passes(), 1)
    self.assertEqual(m.get_minimized_test_input(), b"a;\nb;\nc;\n")
    self.assertEqual(rec.tested, [b"a;\nb;\n"])

  def test_max_exploration_depth(self) -> None:
    # The function's body is a child of the root, since the head and
    # body together would span the entire root.
    src = b"void f()\n{\n  x;\n  keep;\n}\n"
    accept = lambda d: b"keep" in d and balanced(d)

    # With depth 1, only the root's children are tried.
    rec, m = self.run_ma3(src, accept, CPPLanguage(),
                          max_exploration_depth=1)
    self.assertEqual(m.get_minimized_test_input(),
                     b"\n{\n  x;\n  keep;\n}\n")
    self.assertEqual(rec.tested, [
      b"void f()\n",
      b"void f()\n;\n",
      b"\n{\n  x;\n  keep;\n}\n",
    ])

    # With the default, the body's children are tried too, once the
    # body is found to be necessary.
    rec, m = self.run_ma3(src, accept, CPPLanguage())
    self.assertEqual(m.get_minimized_test_input(), b"\n{\n  keep;\n}\n")
    self.assertEqual(rec.tested[3:], [b"\n{\n  x;\n}\n",
                                      b"\n{\n  keep;\n}\n"])
    self.assertEqual([r.ma3_data.exploration_depth
                      for r in rec.starts[3:] if r.ma3_data], [2, 2])

  def test_spec_example(self) -> None:
    # Keep the "g" call.  Everything removable at depth 4 or less goes.
    rec, m = self.run_ma3(SPEC_EXAMPLE,
                          lambda d: b"g()" in d and balanced(d),
                          CPPLanguage())
    self.assertEqual(m.get_minimized_test_input(), dedent_enc("""


      int bar()
      {
        while (1) {
          g();
        }
      }
      """))

    # The nodes are explored right to left and top down.
    self.assertEqual(rec.tested[:3], [
      # "int bar() ...", then its body replaced with ";".
      SPEC_EXAMPLE[:SPEC_EXAMPLE.index(b"\n\nint bar")] + b"\n",
      SPEC_EXAMPLE[:SPEC_EXAMPLE.index(b"\n{\n  while")] + b"\n;\n",
      # "int foo() ...".
      SPEC_EXAMPLE[SPEC_EXAMPLE.index(b"\n\nint bar"):],
    ])


if __name__ == "__main__":
  unittest.main()


# EOF
