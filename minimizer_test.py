# minimizer_test.py
"""
Unit tests for minimizer.
"""

from __future__ import annotations

import unittest
from collections.abc import Callable

from acceptance_test_result import AcceptanceTestResult
from build_tree import build_tree
from ma_factory import make_minimizer
from ma_kind import MinimizationAlgorithmKind
from minimizer import (
  Minimizer,
  NTReplacementFunc,
  StopQueryFunc,
)
from start_report import TestStartReport
from test_util import all_nodes
from token_tree import TTNode
from tokenize_cpp import tokenize_cpp


ACCEPT = AcceptanceTestResult.ACCEPT
REJECT = AcceptanceTestResult.REJECT
INTERRUPTED = AcceptanceTestResult.INTERRUPTED


def no_replacement(node: TTNode) -> bytes | None:
  """Non-trivial replacement function that never provides one."""
  return None


def find_node(root: TTNode, text: bytes) -> TTNode:
  """
  Return the first node, in preorder, under `root` whose text is
  `text`.
  """
  for n in all_nodes(root):
    if n.text() == text:
      return n
  raise AssertionError(f"no node with text {text!r}")


class Recorder:
  """
  Acceptance test and report callbacks for a Minimizer, which record
  what happened.
  """

  def __init__(
    self,
    accept: Callable[[bytes], bool],
    interrupt_at: int | None = None,
  ) -> None:

    # Predicate deciding acceptance.
    self.accept = accept

    # If not None, the test invocation (1-based) that returns
    # INTERRUPTED.
    self.interrupt_at = interrupt_at

    # Inputs passed to the test, in order.
    self.tested: list[bytes] = []

    # Reports received, in order.
    self.starts: list[TestStartReport] = []
    self.finishes: list[tuple[AcceptanceTestResult, bool]] = []

    # The minimizer made by `mk_minimizer`.
    self.minimizer: Minimizer | None = None

  def test(self, data: bytes, report: TestStartReport) -> AcceptanceTestResult:
    # The test receives the report issued just before it.
    assert report is self.starts[-1]

    # Outside the changed range, the candidate is the same as the most
    # recently accepted input.
    assert self.minimizer is not None
    best = self.minimizer.render_candidate({})
    changed = report.changed_byte_range
    assert 0 <= changed.start <= changed.stop <= len(best)
    assert data[:changed.start] == best[:changed.start]
    assert (data[len(data) - (len(best) - changed.stop):] ==
            best[changed.stop:])

    self.tested.append(data)
    if len(self.tested) == self.interrupt_at:
      return INTERRUPTED
    return ACCEPT if self.accept(data) else REJECT

  def mk_minimizer(
    self,
    root: TTNode,
    *,
    max_passes: int | None = None,
    alg_kind: MinimizationAlgorithmKind = MinimizationAlgorithmKind.MA1,
    nt: NTReplacementFunc = no_replacement,
    should_stop: StopQueryFunc | None = None,
  ) -> Minimizer:
    """
    Build a Minimizer object for testing.

    This function is called "mk_minimizer" to avoid using the same name
    as the global make_minimizer.
    """
    self.minimizer = make_minimizer(
      alg_kind                    = alg_kind,
      tree_root                   = root,
      max_passes                  = max_passes,
      test_acceptance             = self.test,
      get_non_trivial_replacement = nt,
      should_stop                 = should_stop,
      report_test_starting        = self.starts.append,
      report_test_finished        = self.finish,
    )
    return self.minimizer

  def finish(self, result: AcceptanceTestResult, memoized: bool) -> None:
    self.finishes.append((result, memoized))


class RenderCandidateTest(unittest.TestCase):
  def render(self, src: bytes, replace: dict[bytes, bytes]) -> bytes:
    """
    Render `src` after replacing, for each key of `replace`, the first
    node with that text by the corresponding value.
    """
    root = build_tree(tokenize_cpp(src))
    m = Recorder(lambda d: True).mk_minimizer(root)
    extra = {id(find_node(root, k)): v for k, v in replace.items()}
    return m.render_candidate(extra)

  def changed_range(
    self,
    src: bytes,
    replace: dict[bytes, bytes],
  ) -> tuple[int, int] | None:
    """
    Like `render`, but return the changed byte range as a tuple, or
    None if there is none.
    """
    root = build_tree(tokenize_cpp(src))
    m = Recorder(lambda d: True).mk_minimizer(root)
    extra = {id(find_node(root, k)): v for k, v in replace.items()}
    r = m.render_candidate_with_range(extra)[1]
    return None if r is None else (r.start, r.stop)

  def test_changed_range_none(self) -> None:
    self.assertIsNone(self.changed_range(b"a;\n", {}))

  def test_changed_range_delete_line(self) -> None:
    # "a;\nb;\nc;\n" becomes "a;\nc;\n".  The range includes the
    # newline before "c", the leading whitespace of the next live token,
    # since that whitespace can change.
    self.assertEqual(
      self.changed_range(b"a;\nb;\nc;\n", {b"\nb;": b""}), (2, 6))

  def test_changed_range_includes_next_whitespace(self) -> None:
    # "a+b" becomes "a b", so the space added before "b" is part of the
    # change, even though "b" itself is not replaced.
    self.assertEqual(self.changed_range(b"a+b", {b"+": b""}), (1, 2))

  def test_changed_range_non_trivial(self) -> None:
    # The final newline token is entirely whitespace, so the range
    # extends to the end.
    self.assertEqual(
      self.changed_range(b"f() {\n  x;\n}\n", {b" {\n  x;\n}": b";"}),
      (3, 13))

  def test_changed_range_at_end(self) -> None:
    # Nothing live follows the change, so it extends to the end.
    self.assertEqual(
      self.changed_range(b"a;\nb;\n", {b"\nb;": b"", b"\n": b""}),
      (2, 6))

  def test_no_replacements(self) -> None:
    src = b"int main()\n{\n  return 0;\n}\n"
    self.assertEqual(self.render(src, {}), src)

  def test_delete_line(self) -> None:
    self.assertEqual(
      self.render(b"a;\nb;\nc;\n", {b"\nb;": b""}),
      b"a;\nc;\n")

  def test_do_not_join_lines(self) -> None:
    # The newline that ends the directive belongs to the deleted token.
    self.assertEqual(
      self.render(b"#define A\nfoo bar\n", {b"\nfoo": b""}),
      b"#define A\nbar\n")

  def test_do_not_coalesce(self) -> None:
    self.assertEqual(self.render(b"a+b", {b"+": b""}), b"a b")

  def test_no_space_needed(self) -> None:
    self.assertEqual(self.render(b"a + b", {b" +": b""}), b"a b")

  def test_start_of_file(self) -> None:
    # Nothing precedes "+", so no space is added.
    self.assertEqual(self.render(b"a+b", {b"a": b""}), b"+b")

  def test_end_of_file(self) -> None:
    # The final newline is restored, since the original input had one.
    self.assertEqual(
      self.render(b"a;\nb;\n", {b"\nb;": b"", b"\n": b""}),
      b"a;\n")

  def test_end_of_file_without_newline(self) -> None:
    # No newline is added if the original input lacked one.
    self.assertEqual(self.render(b"a;\nb;", {b"\nb;": b""}), b"a;")

  def test_final_newline_not_doubled(self) -> None:
    self.assertEqual(self.render(b"a;\nb;\n", {b"\nb;": b""}), b"a;\n")

  def test_final_newline_when_all_removed(self) -> None:
    self.assertEqual(self.render(b"a;\n", {b"a;": b"", b"\n": b""}),
                     b"\n")

  def test_indentation_of_b_not_doubled(self) -> None:
    # B's own horizontal whitespace is dropped in favor of the
    # indentation of the line it now begins.
    self.assertEqual(
      self.render(b"a\n  x; y;\n", {b"\n  x": b"", b";": b""}),
      b"a\n  y;\n")

  def test_non_trivial_keeps_indentation(self) -> None:
    self.assertEqual(
      self.render(b"f() {\n  x;\n}\n", {b"\n  x;": b";"}),
      b"f() {\n  ;\n}\n")

  def test_non_trivial_at_end_of_file(self) -> None:
    # The replacement must not join the directive line, even though
    # nothing live follows it.
    self.assertEqual(
      self.render(b"#define A 1\nint x;\n",
                  {b"\nint x;": b";", b"\n": b""}),
      b"#define A 1\n;\n")

  def test_non_trivial_ignores_newline_inside_token(self) -> None:
    # The comment's leading whitespace has no newline, so neither does
    # the whitespace before its replacement.
    self.assertEqual(
      self.render(b"a; /* x\n  y */ b;", {b" /* x\n  y */": b";"}),
      b"a;; b;")

  def test_ancestor_overrides_descendant(self) -> None:
    # The space before ";" is from the conservative rule against
    # coalescing.
    self.assertEqual(
      self.render(b"f(a, b);", {b"(a, b)": b"()", b"a": b"zzz"}),
      b"f() ;")


class ReportCheckingTestCase(unittest.TestCase):
  """Base class for tests that check the progress reports."""

  def check_granularity(self, r: TestStartReport, m: Minimizer) -> None:
    """
    Check that `r.granularity` is consistent with the algorithm used by
    `m`.

    The default implementation checks the MA1 formula because it is
    treated as the default in this file.
    """
    # MA1 granularity is a number of tokens, halved on each pass.
    self.assertEqual(r.granularity, len(m.tokens) / 2 ** (r.pass_num - 1))

  def check_reports(self, rec: Recorder, m: Minimizer) -> None:
    """Check the consistency of the reports in `rec`."""
    self.assertEqual(len(rec.finishes), len(rec.starts))

    # Every candidate not found in the memoization table is tested.
    self.assertEqual(sum(1 for _, memo in rec.finishes if not memo),
                     len(rec.tested))

    # Memoization means no input is tested twice.
    self.assertEqual(len(set(rec.tested)), len(rec.tested))

    prev: TestStartReport | None = None
    for i, r in enumerate(rec.starts):
      self.assertEqual(r.sequence_num, i + 1)
      self.assertEqual(r.total_num_passes, m._total_num_passes())
      self.check_granularity(r, m)

      self.assertTrue(0 <= r.completion_fraction <= 1)
      if prev is not None:
        self.assertGreaterEqual(r.pass_num, prev.pass_num)
        self.assertLessEqual(r.last_accepted_tok_count,
                             prev.last_accepted_tok_count)
        if r.pass_num == prev.pass_num:
          self.assertGreaterEqual(r.completion_fraction,
                                  prev.completion_fraction)

        # The fields stay in consistent columns.
        self.assertEqual(len(r.to_console_string()),
                         len(prev.to_console_string()))
      prev = r


class MinimizerTest(ReportCheckingTestCase):
  """
  Tests of behavior that is mostly independent of the minimization
  algorithm.  They use MA1, the default.
  """

  def test_empty_input(self) -> None:
    rec = Recorder(lambda d: True)
    m = rec.mk_minimizer(build_tree(tokenize_cpp(b"")))
    self.assertEqual(m.run_minimizer(), ACCEPT)
    self.assertEqual(m.get_minimized_test_input(), b"")
    self.assertEqual(rec.tested, [])

  def test_memo_hits_reported(self) -> None:
    # Nothing can be removed, so later passes repeat candidates that
    # earlier passes already rejected.  (There is no final newline, since
    # removing that would be accepted, via a memo hit, because the
    # rendering restores it.)
    src = b"a;\nb;\nc;\nd;"
    rec = Recorder(lambda d: d == src)
    m = rec.mk_minimizer(build_tree(tokenize_cpp(src)))
    self.assertEqual(m.run_minimizer(), ACCEPT)
    self.check_reports(rec, m)

    memo_results = [r for r, memo in rec.finishes if memo]
    self.assertGreater(len(memo_results), 0)
    self.assertEqual(set(memo_results), {REJECT})
    self.assertEqual(len(rec.starts), len(rec.tested) + len(memo_results))

  def test_initial_input_memoized(self) -> None:
    rec = Recorder(lambda d: True)
    src = b"a;\nb;\n"
    m = rec.mk_minimizer(build_tree(tokenize_cpp(src)))
    self.assertEqual(list(m.memoized_accept.values()), [ACCEPT])
    self.assertEqual(m.render_candidate({}), src)

  def test_current_tok_count(self) -> None:
    rec = Recorder(lambda d: True)
    root = build_tree(tokenize_cpp(b"int a;\nint b;\n"))
    m = rec.mk_minimizer(root)

    # "int", "a", ";", "\nint", "b", ";", "\n".
    self.assertEqual(m.current_tok_count(), 7)

    # Replace a node by modifying `cur_replacement` directly, as if
    # Ctrl-C interrupted `_commit` before it updated `token_live`.
    m.cur_replacement[id(find_node(root, b"\nint b;"))] = b""
    self.assertEqual(m.current_tok_count(), 4)
    self.assertEqual(m.live_tok_count, 7)

  def test_run_twice_fails(self) -> None:
    rec = Recorder(lambda d: True)
    m = rec.mk_minimizer(build_tree(tokenize_cpp(b"a")))
    m.run_minimizer()
    with self.assertRaises(AssertionError):
      m.run_minimizer()


class ShouldStopTest(unittest.TestCase):
  """Tests of the `should_stop` callback."""

  SRC = b"int a;\nint keep;\nint b;\n"

  def make(
    self,
    accept: Callable[[bytes], bool],
    should_stop: Callable[[Recorder], bool],
    src: bytes = SRC,
  ) -> tuple[Recorder, Minimizer]:
    """
    Make a minimizer for `src` that stops when `should_stop`, given the
    recorder, returns True.
    """
    rec = Recorder(accept)
    m = rec.mk_minimizer(
      build_tree(tokenize_cpp(src)),
      should_stop = lambda: should_stop(rec),
    )
    return rec, m

  def test_not_requested(self) -> None:
    # A callback that always returns False has no effect.
    rec, m = self.make(lambda d: b"keep" in d, lambda r: False)
    self.assertEqual(m.run_minimizer(), ACCEPT)
    self.assertFalse(m.stop_requested)
    self.assertEqual(m.get_minimized_test_input(), b"\nkeep\n")
    self.assertEqual(len(rec.tested), 7)

  def test_stop_after_reject(self) -> None:
    # MA1's first candidate, removing everything, is rejected.
    rec, m = self.make(lambda d: b"keep" in d, lambda r: True)
    self.assertEqual(m.run_minimizer(), ACCEPT)
    self.assertTrue(m.stop_requested)
    self.assertEqual(rec.tested, [b"\n"])
    self.assertEqual(rec.finishes, [(REJECT, False)])
    self.assertEqual(m.get_minimized_test_input(), self.SRC)

  def test_stop_keeps_just_accepted(self) -> None:
    # With MA1, the first candidate that is tested and accepted (rather
    # than accepted via a memo hit) is the third.  It is kept when
    # stopping right after it.
    rec, m = self.make(lambda d: b"keep" in d,
                       lambda r: r.finishes[-1] == (ACCEPT, False))
    self.assertEqual(m.run_minimizer(), ACCEPT)
    self.assertTrue(m.stop_requested)
    self.assertEqual(rec.finishes,
                     [(REJECT, False), (ACCEPT, True), (ACCEPT, False)])
    self.assertEqual(m.get_minimized_test_input(), b"int a;\nint keep;\n")
    self.assertEqual(m.get_minimized_test_input(), rec.tested[-1])
    self.assertEqual(m.current_tok_count(), m.live_tok_count)

  def test_called_after_memo_hit(self) -> None:
    # Nothing can be removed, so the second pass begins with a memo hit.
    src = b"a;\nb;\nc;\nd;"
    rec, m = self.make(lambda d: d == src,
                       lambda r: r.finishes[-1][1], src=src)
    self.assertEqual(m.run_minimizer(), ACCEPT)
    self.assertTrue(m.stop_requested)
    self.assertEqual(rec.finishes[-1], (REJECT, True))
    self.assertEqual([memo for _, memo in rec.finishes].count(True), 1)

  def test_normal_termination_takes_precedence(self) -> None:
    # The first candidate removes everything, which ends minimization
    # normally before the callback is consulted.
    rec, m = self.make(lambda d: True, lambda r: True, src=b"a b c")
    self.assertEqual(m.run_minimizer(), ACCEPT)
    self.assertFalse(m.stop_requested)
    self.assertEqual(rec.tested, [b""])
    self.assertEqual(m.get_minimized_test_input(), b"")

  def test_interrupt_takes_precedence(self) -> None:
    # An interrupted test stops minimization without consulting the
    # callback.
    rec = Recorder(lambda d: True, interrupt_at=1)
    calls: list[None] = []

    def should_stop() -> bool:
      calls.append(None)
      return True

    m = rec.mk_minimizer(build_tree(tokenize_cpp(self.SRC)),
                         should_stop=should_stop)
    self.assertEqual(m.run_minimizer(), INTERRUPTED)
    self.assertFalse(m.stop_requested)
    self.assertEqual(calls, [])



if __name__ == "__main__":
  unittest.main()


# EOF
