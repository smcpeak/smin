# ma_hdd_test.py
"""
Unit tests for ma_hdd (Hierarchical Delta Debugging).
"""

from __future__ import annotations

import unittest
from collections.abc import Callable

from build_tree import build_tree
from ma_hdd import HDDMinimizer, compute_candidate_numbers
from ma_kind import MinimizationAlgorithmKind
from minimizer import Minimizer, NTReplacementFunc
from minimizer_test import (
  ACCEPT,
  INTERRUPTED,
  Recorder,
  ReportCheckingTestCase,
  find_node,
  no_replacement,
)
from start_report import TestStartReport
from token_tree import TTNode
from tokenize_cpp import tokenize_cpp


KEEP_SRC = b"int a;\nint keep;\nint b;\n"


def brace_to_semicolon(node: TTNode) -> bytes | None:
  """Non-trivial replacement function: replace a brace group with ";"."""
  if node.is_delim_group() and node.first_token().text.strip() == b"{":
    return b";"
  return None


class ComputeCandidateNumbersTest(unittest.TestCase):
  def test_values(self) -> None:
    self.assertEqual(compute_candidate_numbers(1), (1, {1: 0}))
    self.assertEqual(compute_candidate_numbers(2), (2, {1: 0}))
    self.assertEqual(compute_candidate_numbers(3), (3, {1: 0}))

    # The example in the spec.
    self.assertEqual(compute_candidate_numbers(4), (6, {2: 0, 1: 2}))

    # The last run at G=2 is shorter.
    self.assertEqual(compute_candidate_numbers(5), (8, {2: 0, 1: 3}))

    # Halving does not always yield a divisor of the previous G.
    self.assertEqual(compute_candidate_numbers(10),
                     (17, {5: 0, 2: 2, 1: 7}))


class HDDTest(ReportCheckingTestCase):
  """Tests of the HDD algorithm."""

  def check_granularity(self, r: TestStartReport, m: Minimizer) -> None:
    # The granularity is a number of nodes.
    self.assertEqual(r.granularity, int(r.granularity))
    self.assertGreaterEqual(r.granularity, 1)

  def make_hdd(
    self,
    rec: Recorder,
    src: bytes,
    nt: NTReplacementFunc = no_replacement,
    max_passes: int | None = None,
  ) -> Minimizer:
    """Make an HDD minimizer for `src` that reports to `rec`."""
    return rec.mk_minimizer(build_tree(tokenize_cpp(src)), nt=nt,
                            max_passes=max_passes,
                            alg_kind=MinimizationAlgorithmKind.HDD)

  def run_hdd(
    self,
    src: bytes,
    accept: Callable[[bytes], bool],
    nt: NTReplacementFunc = no_replacement,
    max_passes: int | None = None,
  ) -> tuple[Recorder, Minimizer]:
    """
    Run HDD on `src` with acceptance predicate `accept`, check the
    reports, and return the recorder and minimizer.
    """
    rec = Recorder(accept)
    m = self.make_hdd(rec, src, nt, max_passes)
    self.assertEqual(m.run_minimizer(), ACCEPT)
    self.assertTrue(accept(m.get_minimized_test_input()))
    self.check_reports(rec, m)
    return rec, m

  def test_kind(self) -> None:
    m = self.make_hdd(Recorder(lambda d: True), b"a")
    self.assertIsInstance(m, HDDMinimizer)
    self.assertEqual(m.get_ma_kind(), MinimizationAlgorithmKind.HDD)

  def test_empty_input(self) -> None:
    rec, m = self.run_hdd(b"", lambda d: True)
    self.assertEqual(m._total_num_passes(), 0)
    self.assertEqual(m.get_minimized_test_input(), b"")
    self.assertEqual(rec.starts, [])

  def test_accept_everything(self) -> None:
    # The root has three children, so G starts at 1.  Removing the last
    # one ends minimization, as nothing is left.
    rec, m = self.run_hdd(b"a b c", lambda d: True)
    self.assertEqual(m.get_minimized_test_input(), b"")
    self.assertEqual(rec.tested, [b"a b", b"a", b""])
    self.assertEqual([r.granularity for r in rec.starts], [1, 1, 1])

  def test_keep_one_identifier(self) -> None:
    # The root's children are the three lines and the final newline.
    rec, m = self.run_hdd(KEEP_SRC, lambda d: b"keep" in d)
    self.assertEqual(m.get_minimized_test_input(), b"\nkeep\n")
    self.assertEqual(m._total_num_passes(), 2)
    self.assertEqual(rec.tested, [
      # Level 1, G=2: The last two children, then the first two.
      b"int a;\nint keep;\n",
      b"\n",

      # G=1: Only the first two lines remain, last first.  Unlike MA2,
      # there is no recursion into the necessary "keep" line.
      b"int a;\n",
      b"\nint keep;\n",

      # Level 2, G=1: The three tokens of the only surviving line.
      b"\nint keep\n",
      b"\nint\n",
      b"\nkeep\n",
    ])
    self.assertEqual([r.pass_num for r in rec.starts], [1] * 4 + [2] * 3)
    self.assertEqual([r.granularity for r in rec.starts],
                     [2, 2, 1, 1, 1, 1, 1])

    # Level 1 has Cm=6, with G=1 starting at C=2.  Level 2 has Cm=3.
    self.assertEqual([r.completion_fraction for r in rec.starts],
                     [0/6, 1/6, 2/6, 3/6, 0/3, 1/3, 2/3])

  def test_report_shortened_iteration(self) -> None:
    # Four tokens get removed at G=2, leaving no candidates for the
    # final two of those G=2 runs, and so C jumps when G changes.
    src = b"int f() { a; b; c; d; }\n"
    rec, m = self.run_hdd(
      src, lambda d: b"c;" in d and d.count(b"{") == d.count(b"}"))
    self.assertEqual(m.get_minimized_test_input(), b" { c; }\n")

    # Level 3 is the eight tokens between the braces.  Its Cm is
    # 2 + 4 + 8, and the G=1 iteration starts at C=6.
    level3 = [r for r in rec.starts if r.pass_num == 3]
    self.assertEqual([r.granularity for r in level3], [4, 4, 2, 2, 1, 1])
    self.assertEqual([r.completion_fraction for r in level3],
                     [0/14, 1/14, 2/14, 3/14, 6/14, 7/14])

  def test_max_passes(self) -> None:
    # With one pass, only the children of the root are considered.
    rec, m = self.run_hdd(KEEP_SRC, lambda d: b"keep" in d, max_passes=1)
    self.assertEqual(m._total_num_passes(), 1)
    self.assertEqual(m.get_minimized_test_input(), b"\nint keep;\n")
    self.assertEqual({r.pass_num for r in rec.starts}, {1})

    # A limit above the tree depth has no effect.
    rec, m = self.run_hdd(KEEP_SRC, lambda d: b"keep" in d, max_passes=5)
    self.assertEqual(m._total_num_passes(), 2)
    self.assertEqual(m.get_minimized_test_input(), b"\nkeep\n")

  def test_finishes_before_last_pass(self) -> None:
    # The deepest nodes are in the function body, which is removed at
    # level 2, so level 3 is empty and never reached.
    src = b"void f() { a; b; }\n"
    rec, m = self.run_hdd(src, lambda d: b"f" in d)
    self.assertEqual(m.get_minimized_test_input(), b" f\n")
    self.assertEqual(m._total_num_passes(), 3)
    self.assertEqual(max(r.pass_num for r in rec.starts), 2)

  def test_delimiters_not_removed(self) -> None:
    # No candidate removes a delimiter without its partner, even when
    # the only acceptance criterion would allow that.
    src = b"int f(int a) { x; y; }\nint g[] = { 1, 2 };\n"
    rec, m = self.run_hdd(src, lambda d: b"x" in d)
    for d in rec.tested:
      for opener, closer in [(b"{", b"}"), (b"(", b")"), (b"[", b"]")]:
        self.assertEqual(d.count(opener), d.count(closer), d)

    # The group is the only way to get rid of them, and that fails here.
    self.assertEqual(m.get_minimized_test_input(), b" { x }\n")

  def test_nodes_at_level(self) -> None:
    src = b"void f() { x; }\nint keep;\n"
    root = build_tree(tokenize_cpp(src))
    rec = Recorder(lambda d: True)
    m = rec.mk_minimizer(root, alg_kind=MinimizationAlgorithmKind.HDD)
    assert isinstance(m, HDDMinimizer)

    def level_text(level: int) -> list[bytes]:
      return [n.text() for n in m._nodes_at_level(root, level)]

    self.assertEqual(level_text(0), [src])
    self.assertEqual(level_text(1),
                     [b"void f() { x; }", b"\nint keep;", b"\n"])

    # Nodes with different parents, in order.
    self.assertEqual(level_text(2), [
      b"void", b" f", b"()", b" { x; }",
      b"\nint", b" keep", b";",
    ])

    # The delimiters of "()" and "{ x; }" are excluded, leaving only the
    # contents of the latter.
    self.assertEqual(level_text(3), [b" x", b";"])

    # There is nothing deeper.
    self.assertEqual(level_text(4), [])

    # A replaced node is excluded.
    m.cur_replacement[id(find_node(root, b" keep"))] = b""
    self.assertEqual(level_text(2), [
      b"void", b" f", b"()", b" { x; }",
      b"\nint", b";",
    ])

    # So are the descendants of a replaced node, even though they are
    # not themselves marked as replaced.
    m.cur_replacement[id(find_node(root, b" { x; }"))] = b";"
    self.assertEqual(level_text(3), [])

  def test_non_contiguous_run(self) -> None:
    # Level 3 is ["a", "b", "c", "d"], so at G=2, the runs have nodes
    # with different parents, and delimiters in between them.
    src = b"(a)(b)(c)(d)\n"
    rec, m = self.run_hdd(src, lambda d: d.count(b"(") == 4 and b"a" in d)

    # Rendering separates tokens that were not adjacent originally.
    self.assertEqual(m.get_minimized_test_input(), b"(a)( )( )( )\n")

    level3 = [r for r in rec.starts if r.pass_num == 3]
    self.assertEqual([r.granularity for r in level3], [2, 2, 1, 1])
    self.assertEqual([r.removed_tok_count for r in level3], [2, 2, 1, 1])
    self.assertIn(b"(a)(b)( )( )\n", rec.tested)

  def test_non_trivial_replacement(self) -> None:
    # Removing the function body is rejected, but replacing it with ";"
    # is accepted.
    rec, m = self.run_hdd(b"void f() { x; }\nint keep;\n",
                          lambda d: b"keep" in d and b"f();" in d,
                          brace_to_semicolon)
    self.assertEqual(m.get_minimized_test_input(), b" f();\nint keep;\n")

    # The replacement is tried right after removal is rejected.
    i = rec.tested.index(b"void f();\nint keep;\n")
    self.assertEqual(rec.tested[i-1], b"void f()\nint keep;\n")

    # Its C is that of the removal, plus 0.5, on level 2, where Cm=10.
    j = [k for k, (_, memo) in enumerate(rec.finishes) if not memo][i]
    self.assertEqual(rec.starts[j-1].completion_fraction, 6/10)
    self.assertEqual(rec.starts[j].completion_fraction, 6.5/10)
    self.assertEqual(rec.starts[j+1].completion_fraction, 7/10)

    # The only nodes on level 3 are inside the replaced node, so that
    # level is empty.
    self.assertEqual(
      [r.removed_tok_count for r in rec.starts if r.pass_num == 3], [])

  def test_non_trivial_replacement_only_at_g1(self) -> None:
    # The five children of the root yield a one-element run at G=2.
    # That has no non-trivial attempt; the attempt waits until G=1.
    # The run is the last child, which has five tokens.
    src = b"a;\nb;\nc;\nd;\ne { x; }"
    tried: list[int] = []
    rec = Recorder(lambda d: d == src)

    def nt(node: TTNode) -> bytes | None:
      tried.append(int(rec.starts[-1].granularity))
      return brace_to_semicolon(node)

    m = self.make_hdd(rec, src, nt)
    self.assertEqual(m.run_minimizer(), ACCEPT)
    self.check_reports(rec, m)
    self.assertEqual(rec.starts[0].granularity, 2)
    self.assertEqual(rec.starts[0].removed_tok_count, 5)
    self.assertGreater(len(tried), 0)
    self.assertEqual(set(tried), {1})

  def test_interrupted(self) -> None:
    rec = Recorder(lambda d: b"keep" in d, interrupt_at=3)
    m = self.make_hdd(rec, KEEP_SRC)
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

    _, m = self.run_hdd(src, accept)
    self.assertLess(len(m.get_minimized_test_input()), len(src) // 4)


if __name__ == "__main__":
  unittest.main()


# EOF
