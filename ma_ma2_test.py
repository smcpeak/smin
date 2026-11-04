# ma_ma2_test.py
"""
Unit tests for ma_ma2 (Minimization Algorithm 2).
"""

from __future__ import annotations

import unittest
from collections.abc import Callable

from build_tree import build_tree
from ma_kind import MinimizationAlgorithmKind
from minimizer import Minimizer, NTReplacementFunc
from minimizer_test import (
  ACCEPT,
  INTERRUPTED,
  Recorder,
  ReportCheckingTestCase,
  no_replacement,
)
from start_report import TestStartReport
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
    nt: NTReplacementFunc = no_replacement,
    max_passes: int | None = None,
  ) -> tuple[Recorder, Minimizer]:
    """
    Run MA2 on `src` with acceptance predicate `accept`, check the
    reports, and return the recorder and minimizer.
    """
    rec = Recorder(accept)
    m = rec.mk_minimizer(build_tree(tokenize_cpp(src)), nt=nt,
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
    def nt(node: TTNode) -> bytes | None:
      if node.delim_group and node.first_token().text.strip() == b"{":
        return b";"
      return None

    rec, m = self.run_ma2(b"void f() { x; }\nint keep;\n",
                          lambda d: b"keep" in d and b"f();" in d, nt)
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
    m = rec.mk_minimizer(
      build_tree(tokenize_cpp(b"int a;\nint keep;\nint b;\n")),
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


if __name__ == "__main__":
  unittest.main()


# EOF
