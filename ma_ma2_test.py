# ma_ma2_test.py
"""
Unit tests for ma_ma2 (Minimization Algorithm 2).
"""

from __future__ import annotations

import unittest
from collections.abc import Callable
from unittest import mock

from build_tree import build_tree
from lang_cpp import CPPLanguage
from language import Language
from ma_ma2 import MA2Minimizer
from ma_kind import MinimizationAlgorithmKind
from minimizer import Minimizer
from minimizer_test import (
  ACCEPT,
  INTERRUPTED,
  Recorder,
  ReportCheckingTestCase,
  TEST_LANGUAGE,
)
from start_report import TestStartReport
from test_util import all_nodes
from token_tree import TTNode
from tokenize_cpp import tokenize_cpp


class MA2Test(ReportCheckingTestCase):
  """Tests of Minimization Algorithm 2."""

  def check_granularity(self, r: TestStartReport, m: Minimizer) -> None:
    # The granularity is a number of nodes.
    self.assertEqual(r.granularity, int(r.granularity))
    self.assertGreaterEqual(r.granularity, 1)

  def run_ma2(
    self,
    src: bytes,
    accept: Callable[[bytes], bool],
    language: Language = TEST_LANGUAGE,
    max_passes: int | None = None,
  ) -> tuple[Recorder, Minimizer]:
    """
    Run MA2 on `src` with acceptance predicate `accept`, check the
    reports, and return the recorder and minimizer.
    """
    rec = Recorder(accept)
    m = rec.mk_min_for_text(src,
      language=language,
      max_passes=max_passes,
      alg_kind=MinimizationAlgorithmKind.MA2)
    self.assertEqual(m.run_minimizer(), ACCEPT)
    self.assertTrue(accept(m.get_minimized_test_input()))
    self.check_reports(rec, m)
    return rec, m

  def test_empty_input(self) -> None:
    rec, m = self.run_ma2(b"", lambda d: True)
    self.assertEqual(m._total_num_passes(), 0)
    self.assertEqual(m.get_minimized_test_input(), b"")
    self.assertEqual(rec.starts, [])

  def test_accept_everything(self) -> None:
    # The root has three children, so the first candidate removes one.
    # After that is accepted, the granularity doubles to cover the
    # remaining two.
    rec, m = self.run_ma2(b"a b c", lambda d: True)
    self.assertEqual(m.get_minimized_test_input(), b"")
    self.assertEqual(rec.tested, [b"a b", b""])
    self.assertEqual([r.granularity for r in rec.starts], [1, 2])

  def test_keep_one_identifier(self) -> None:
    # The root's children are the three lines and the final newline.
    rec, m = self.run_ma2(b"int a;\nint keep;\nint b;\n",
                          lambda d: b"keep" in d)
    self.assertEqual(m.get_minimized_test_input(), b"\nkeep\n")
    self.assertEqual(m._total_num_passes(), 2)
    self.assertEqual(rec.tested, [
      # Pass 1.  Since the root is not a delimiter group, the first
      # candidate removes only half of its children.  That is accepted,
      # so the granularity doubles, but is clamped to the two children
      # still in scope.
      b"int a;\nint keep;\n",
      b"\n",
      # The granularity is cut to 1, the "keep" line is found to be
      # necessary, and the line before it is removed.
      b"int a;\n",
      b"\nint keep;\n",

      # Pass 2.  First, the "keep" line, the only surviving child of
      # the root, is tried again; that is a memo hit.  Then, since it is
      # necessary, we immediately recurse into it, removing its
      # children from last to first.
      b"\nint keep\n",
      b"\nint\n",
      b"\nkeep\n",
    ])
    self.assertEqual([r.granularity for r in rec.starts],
                     [2, 2, 1, 1, 1, 1, 2, 1, 1])
    self.assertEqual([memo for _, memo in rec.finishes],
                     [False] * 4 + [True, False, True, False, False])

  def test_max_passes(self) -> None:
    # With one pass, only the children of the root are considered.
    rec, m = self.run_ma2(b"int a;\nint keep;\nint b;\n",
                          lambda d: b"keep" in d, max_passes=1)
    self.assertEqual(m._total_num_passes(), 1)
    self.assertEqual(m.get_minimized_test_input(), b"\nint keep;\n")
    self.assertEqual({r.pass_num for r in rec.starts}, {1})

    # A limit above the tree depth has no effect.
    rec, m = self.run_ma2(b"int a;\nint keep;\nint b;\n",
                          lambda d: b"keep" in d, max_passes=5)
    self.assertEqual(m._total_num_passes(), 2)
    self.assertEqual(m.get_minimized_test_input(), b"\nkeep\n")

  def test_nothing_removable(self) -> None:
    # Every child is necessary.  Each is tried individually, and
    # recursed into on the second pass, where the candidates that
    # repeat the first pass are memo hits.  (There is no final newline,
    # since removing that would be accepted, via a memo hit, because
    # the rendering restores it.)
    src = b"a;\nb;\nc;\nd;"
    rec, m = self.run_ma2(src, lambda d: d == src)
    self.assertEqual(m.get_minimized_test_input(), src)

    # Pass 1: half of the four lines, then each line from last to
    # first.  Pass 2: the same, but after each line is found necessary,
    # its two children, last first.
    pass1 = [r for r in rec.starts if r.pass_num == 1]
    pass2 = [r for r in rec.starts if r.pass_num == 2]
    self.assertEqual([r.removed_tok_count for r in pass1],
                     [4, 2, 2, 2, 2])
    self.assertEqual([r.removed_tok_count for r in pass2],
                     [4, 2, 1, 1] * 1 + [2, 1, 1] * 3)
    memo = [m for _, m in rec.finishes]
    self.assertEqual(memo[5:],
                     [True, True, False, False] + [True, False, False] * 3)

  def test_delimiter_group_interior(self) -> None:
    # Within a delimiter group, the first candidate removes the entire
    # interior, and the delimiters themselves are never removed.
    src = b"int f() { a; b; c; d; }\n"
    rec, m = self.run_ma2(
      src, lambda d: b"c;" in d and d.count(b"{") == d.count(b"}"))
    self.assertEqual(m.get_minimized_test_input(), b" { c; }\n")
    self.assertIn(b" { }\n", rec.tested)
    for d in rec.tested:
      self.assertEqual(d.count(b"{"), d.count(b"}"))
      self.assertEqual(d.count(b"("), d.count(b")"))

  def test_non_trivial_replacement(self) -> None:
    # Removing the function body is rejected, but replacing it with ";"
    # is accepted.
    rec, m = self.run_ma2(b"void f() { x; }\nint keep;\n",
                          lambda d: b"keep" in d and b"f();" in d,
                          CPPLanguage())
    self.assertEqual(m.get_minimized_test_input(), b" f();\nkeep\n")

    # The replacement is tried right after removal is rejected, and the
    # granularity stays at 1 afterward.
    i = rec.tested.index(b"void f();\nint keep;\n")
    self.assertEqual(rec.tested[i-1], b"void f()\nint keep;\n")
    self.assertEqual(rec.tested[i+1], b"void f;\nint keep;\n")
    # Index in `rec.starts` of the report for `rec.tested[i]`.
    j = [k for k, (_, memo) in enumerate(rec.finishes) if not memo][i]
    self.assertEqual(rec.starts[j].removed_tok_count, 4)
    self.assertEqual([r.granularity for r in rec.starts[j:j+3]], [1, 1, 1])

  def test_interrupted(self) -> None:
    rec = Recorder(lambda d: b"keep" in d, interrupt_at=3)
    m = rec.mk_min_for_text(
      b"int a;\nint keep;\nint b;\n",
      alg_kind=MinimizationAlgorithmKind.MA2)
    self.assertEqual(m.run_minimizer(), INTERRUPTED)
    self.assertEqual(rec.finishes[-1], (INTERRUPTED, False))

    # The result is the last accepted input.
    self.assertEqual(m.get_minimized_test_input(), b"int a;\nint keep;\n")

  def test_result_is_accepted(self) -> None:
    # A larger input, where acceptance requires several scattered
    # pieces, and the delimiters to be balanced.
    src = b"""\
#include <stdio.h>

struct S {
  int x;
  int y;
};

int helper(int a, int b)
{
  return a + b;
}

int main()
{
  struct S s = { 1, 2 };
  printf("%d\\n", helper(s.x, s.y));
  return 0;
}
"""
    def accept(d: bytes) -> bool:
      return (b"helper" in d and b"printf" in d and
              d.count(b"{") == d.count(b"}") and
              d.count(b"(") == d.count(b")"))

    _, m = self.run_ma2(src, accept)
    self.assertLess(len(m.get_minimized_test_input()), len(src) // 4)


is_brace_group = CPPLanguage().is_brace_group


class MA2BraceGroupsTest(ReportCheckingTestCase):
  """Tests of MA2 with --ma2-brace-groups."""

  def check_granularity(self, r: TestStartReport, m: Minimizer) -> None:
    # The granularity is a number of nodes.
    self.assertEqual(r.granularity, int(r.granularity))
    self.assertGreaterEqual(r.granularity, 1)

  def make(
    self,
    rec: Recorder,
    src: bytes,
    max_passes: int | None = None,
  ) -> MA2Minimizer:
    """Make an MA2 minimizer for `src`, using brace group mode."""
    m = rec.mk_min_for_text(src,
      max_passes=max_passes,
      alg_kind=MinimizationAlgorithmKind.MA2,
      ma2_brace_groups=True)
    assert isinstance(m, MA2Minimizer)
    return m

  def num_passes(self, src: bytes, max_passes: int | None = None) -> int:
    m = self.make(Recorder(lambda d: True), src, max_passes)
    return m._total_num_passes()

  def test_num_passes(self) -> None:
    # Edges from the root count, but there are no brace groups.
    self.assertEqual(self.num_passes(b""), 0)
    self.assertEqual(self.num_passes(b"int a;\n"), 1)

    # The edge from the brace group to its interior also counts.
    self.assertEqual(self.num_passes(b"int f() { a; }\n"), 2)

    # Each level of brace nesting adds one.
    self.assertEqual(
      self.num_passes(b"void f() {\n  if (x) {\n    y;\n  }\n}\n"), 3)

    # The edges to delimiters do not count, so an empty brace group does
    # not add a pass, since it has nothing to remove.
    self.assertEqual(self.num_passes(b"void f() {}\n"), 1)

    # A brace group that is a child of the root still adds a pass for
    # its interior.  (Counting only the edges *into* brace groups would
    # yield 1 here, and the interior would never be reached.)
    src = b"{\n  x y;\n  keep;\n}\n"
    self.assertEqual(self.num_passes(src), 2)
    self.assertTrue(is_brace_group(build_tree(tokenize_cpp(src)).children[0]))

  def test_num_passes_max_passes(self) -> None:
    src = b"void f() {\n  if (x) {\n    y;\n  }\n}\n"
    self.assertEqual(self.num_passes(src, max_passes=2), 2)
    self.assertEqual(self.num_passes(src, max_passes=9), 3)

  def test_get_brace_groups(self) -> None:
    m = self.make(Recorder(lambda d: True),
                  b"x = f({1}, {2}) { {4} } {3};\n")
    line = m.tree_root.children[0]

    def texts(n: TTNode) -> list[bytes]:
      return [bg.text() for bg in m._get_brace_groups(n)]

    # Right to left, searching inside the parentheses, but not inside a
    # brace group.
    self.assertEqual(texts(line), [b" {3}", b" { {4} }", b" {2}", b"{1}"])

    # A brace group yields only itself.
    outer = line.children[4]
    self.assertEqual(texts(outer), [b" { {4} }"])

    # Without any brace groups, nothing is yielded.
    self.assertEqual(texts(line.children[0]), [])

    # Replaced nodes are skipped.
    m.cur_replacement[id(line.children[3])] = b""
    self.assertEqual(texts(line), [b" {3}", b" { {4} }"])

  def test_trace(self) -> None:
    rec = Recorder(lambda d: b"keep" in d and d.count(b"{") == d.count(b"}"))
    m = self.make(rec, b"int f() { a; keep; }\n")
    self.assertEqual(m.run_minimizer(), ACCEPT)
    self.check_reports(rec, m)

    # Only the interior of the brace group gets minimized, since nothing
    # else in the line is a child of the root or of a brace group.
    self.assertEqual(m.get_minimized_test_input(), b"int f() { keep }\n")
    self.assertEqual(rec.tested, [
      # Pass 1: The children of the root: the line, then the newline,
      # the latter being a memo hit.
      b"\n",

      # Pass 2: The line is necessary, so recurse into its brace group,
      # and remove its interior from last to first.
      b"int f() { }\n",
      b"int f() { a; }\n",
      b"int f() { a; keep }\n",
      b"int f() { a }\n",
      b"int f() { a keep }\n",
      b"int f() { keep }\n",
    ])
    self.assertEqual([r.pass_num for r in rec.starts], [1] * 2 + [2] * 8)

  def test_candidates(self) -> None:
    # Every candidate replaces children of the root or of brace groups,
    # but not their delimiters.
    src = b"""\
struct S {
  int x;
  int y;
};

int f(int a)
{
  if (a) {
    return g({1, 2}, a);
  }
  return 0;
}
"""
    rec = Recorder(lambda d: b"return 0" in d and b"g(" in d and
                   d.count(b"{") == d.count(b"}"))
    m = self.make(rec, src)
    parent = {
      id(c): n
      for n in all_nodes(m.tree_root)
      for c in n.children
    }

    with mock.patch.object(m, "_try_candidate",
                           wraps=m._try_candidate) as spy:
      self.assertEqual(m.run_minimizer(), ACCEPT)
    self.check_reports(rec, m)

    candidates = [n for call in spy.call_args_list for n in call.args[1]]
    self.assertGreater(len(candidates), 0)
    for n in candidates:
      p = parent[id(n)]
      if p is not m.tree_root:
        self.assertTrue(is_brace_group(p), n.text())
        self.assertIsNot(n, p.children[0])
        self.assertIsNot(n, p.children[-1])

    # Every level of brace nesting, down to "{1, 2}", was reached.
    self.assertEqual(m._total_num_passes(), 4)
    self.assertIn(b"{1, 2}",
                  [parent[id(n)].text().strip() for n in candidates])
    self.assertEqual(max(r.pass_num for r in rec.starts), 4)

  def test_requires_ma2(self) -> None:
    for kind in (MinimizationAlgorithmKind.MA1,
                 MinimizationAlgorithmKind.HDD):
      with self.assertRaises(AssertionError):
        Recorder(lambda d: True).mk_min_for_text(
          b"a;\n",
          alg_kind=kind,
          ma2_brace_groups=True)


if __name__ == "__main__":
  unittest.main()


# EOF
