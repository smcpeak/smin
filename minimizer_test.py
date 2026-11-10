# minimizer_test.py
"""
Unit tests for minimizer.
"""

from __future__ import annotations

import unittest
from collections.abc import Callable

from acceptance_test_result import AcceptanceTestResult
from acceptance_tester import AcceptanceTester
from build_tree import build_tree
from lang_cpp import CPPLanguage
from language import Language
from ma_ma1 import MA1MinimizerSelector
from min_alg_factory import make_minimizer
from min_alg_selector import MinimizerAlgorithmSelector
from minimizer import Minimizer
from minimizer_options import (
  MinimizerOptions,
  StopQueryFunc,
)
from start_report import TestStartReport
from test_util import all_nodes
from token_tree import TokenTree, TTNode
from tokenize_cpp import tokenize_cpp
from tokenizer import Tokenizer


ACCEPT = AcceptanceTestResult.ACCEPT
REJECT = AcceptanceTestResult.REJECT
INTERRUPTED = AcceptanceTestResult.INTERRUPTED


def no_replacement(node: TTNode) -> bytes | None:
  """Non-trivial replacement function that never provides one."""
  return None


class FuncLanguage:
  """
  A `Language` for tests that is like C++, except that its non-trivial
  replacement query is delegated to a function, which by default never
  provides a replacement.
  """

  def __init__(
    self,
    nt: Callable[[TTNode], bytes | None] = no_replacement,
  ) -> None:
    self.nt = nt
    self.cpp = CPPLanguage()

  def make_tokenizer(self) -> Tokenizer:
    return self.cpp.make_tokenizer()

  def non_trivial_replacement(self, node: TTNode) -> bytes | None:
    return self.nt(node)

  def is_brace_group(self, node: TTNode) -> bool:
    return self.cpp.is_brace_group(node)


# The default language for tests: C++, but with no non-trivial
# replacements, so tests need only consider removal.
TEST_LANGUAGE: Language = FuncLanguage()


def find_node(root: TTNode, text: bytes) -> TTNode:
  """
  Return the first node, in preorder, under `root` whose text is
  `text`.
  """
  for n in all_nodes(root):
    if n.text() == text:
      return n
  raise AssertionError(f"no node with text {text!r}")


class Recorder(AcceptanceTester):
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

  def test_acceptance(
    self,
    data: bytes,
    report: TestStartReport,
  ) -> AcceptanceTestResult:
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

  def min_opts(
    self,
    *,
    selector: MinimizerAlgorithmSelector | None = None,
    max_passes: int | None = None,
    language: Language = TEST_LANGUAGE,
    should_stop: StopQueryFunc | None = None,
  ) -> MinimizerOptions:
    """Build minimizer options."""
    if not selector:
      selector = MA1MinimizerSelector()
    return MinimizerOptions(
      selector         = selector,
      max_passes       = max_passes,
      acceptance       = self,
      language         = language,
      should_stop      = should_stop,
    )

  def mk_minimizer(
    self,
    tree: TokenTree,
    opts: MinimizerOptions | None = None,
  ) -> Minimizer:
    """
    Build a Minimizer object for testing.

    This function is called "mk_minimizer" to avoid using the same name
    as the global make_minimizer.
    """
    self.minimizer = make_minimizer(
      options   = opts if opts else self.min_opts(),
      tree      = tree,
    )
    return self.minimizer

  def mk_min_for_text(
    self,
    src: bytes,
    opts: MinimizerOptions | None = None,
  ) -> Minimizer:
    """
    Return `mk_minimizer(build_tree(tokenize_cpp(src)), <args>)`.
    """
    tree: TokenTree = build_tree(tokenize_cpp(src))
    return self.mk_minimizer(tree, opts)

  def report_test_starting(self, report: TestStartReport) -> None:
    self.starts.append(report)

  def report_test_finished(
    self,
    result: AcceptanceTestResult,
    memoized: bool,
  ) -> None:
    self.finishes.append((result, memoized))


class RenderCandidateTest(unittest.TestCase):
  def render(self, src: bytes, replace: dict[bytes, bytes]) -> bytes:
    """
    Render `src` after replacing, for each key of `replace`, the first
    node with that text by the corresponding value.
    """
    tree = build_tree(tokenize_cpp(src))
    m = Recorder(lambda d: True).mk_minimizer(tree)
    extra = {id(find_node(tree.root, k)): v for k, v in replace.items()}
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
    tree = build_tree(tokenize_cpp(src))
    m = Recorder(lambda d: True).mk_minimizer(tree)
    extra = {id(find_node(tree.root, k)): v for k, v in replace.items()}
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
    # Nothing live follows the change, so the range extends to the
    # EOF whitespace, which is never changed.
    self.assertEqual(
      self.changed_range(b"f() {\n  x;\n}\n", {b" {\n  x;\n}": b";"}),
      (3, 12))

  def test_changed_range_at_end(self) -> None:
    # Nothing live follows the change, so it extends to the EOF
    # whitespace.
    self.assertEqual(
      self.changed_range(b"a;\nb;\n", {b"\nb;": b""}),
      (2, 5))

  def test_changed_range_at_end_without_eof_ws(self) -> None:
    # Without EOF whitespace, the range extends to the end.
    self.assertEqual(
      self.changed_range(b"a;\nb;", {b"\nb;": b""}),
      (2, 5))

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
    # The EOF whitespace, which is not part of the tree, is always
    # appended.
    self.assertEqual(
      self.render(b"a;\nb;\n\n", {b"\nb;": b""}),
      b"a;\n\n")

  def test_end_of_file_without_newline(self) -> None:
    # No newline is added if the original input lacked one.
    self.assertEqual(self.render(b"a;\nb;", {b"\nb;": b""}), b"a;")

  def test_final_newline_not_doubled(self) -> None:
    self.assertEqual(self.render(b"a;\nb;\n", {b"\nb;": b""}), b"a;\n")

  def test_final_newline_when_all_removed(self) -> None:
    self.assertEqual(self.render(b"a;\n", {b"a;": b""}), b"\n")

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
                  {b"\nint x;": b";"}),
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

  # True to check that, within a pass, the completion fraction never
  # decreases.
  CHECK_FRACTION_MONOTONIC: bool = True

  # True to check that every progress report has the same length, so
  # its fields stay in consistent columns.
  CHECK_FIXED_COLUMNS: bool = True

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
        if self.CHECK_FRACTION_MONOTONIC and r.pass_num == prev.pass_num:
          self.assertGreaterEqual(r.completion_fraction,
                                  prev.completion_fraction)

        # The fields stay in consistent columns.
        if self.CHECK_FIXED_COLUMNS:
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
    m = rec.mk_min_for_text(b"")
    self.assertEqual(m.run_minimizer(), ACCEPT)
    self.assertEqual(m.get_minimized_test_input(), b"")
    self.assertEqual(rec.tested, [])

  def test_memo_hits_reported(self) -> None:
    # Nothing can be removed, so later passes repeat candidates that
    # earlier passes already rejected.
    src = b"a;\nb;\nc;\nd;\n"
    rec = Recorder(lambda d: d == src)
    m = rec.mk_min_for_text(src)
    self.assertEqual(m.run_minimizer(), ACCEPT)
    self.check_reports(rec, m)

    memo_results = [r for r, memo in rec.finishes if memo]
    self.assertGreater(len(memo_results), 0)
    self.assertEqual(set(memo_results), {REJECT})
    self.assertEqual(len(rec.starts), len(rec.tested) + len(memo_results))

  def test_initial_input_memoized(self) -> None:
    rec = Recorder(lambda d: True)
    src = b"a;\nb;\n"
    m = rec.mk_min_for_text(src)
    self.assertEqual(list(m.memoized_accept.values()), [ACCEPT])
    self.assertEqual(m.render_candidate({}), src)

  def test_current_tok_count(self) -> None:
    rec = Recorder(lambda d: True)
    tree = build_tree(tokenize_cpp(b"int a;\nint b;\n"))
    m = rec.mk_minimizer(tree)

    # "int", "a", ";", "\nint", "b", ";".  The final "\n" is EOF
    # whitespace, which is not counted.
    self.assertEqual(m.current_tok_count(), 6)

    # Replace a node by modifying `cur_replacement` directly, as if
    # Ctrl-C interrupted `_commit` before it updated `token_live`.
    m.cur_replacement[id(find_node(tree.root, b"\nint b;"))] = b""
    self.assertEqual(m.current_tok_count(), 3)
    self.assertEqual(m.live_tok_count, 6)

  def test_run_twice_fails(self) -> None:
    rec = Recorder(lambda d: True)
    m = rec.mk_min_for_text(b"a")
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
    Make a minimizer for `src` that stops when `should_stop` returns
    True.
    """
    rec = Recorder(accept)
    m = rec.mk_min_for_text(src, rec.min_opts(
      should_stop = lambda: should_stop(rec)),
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
    # With MA1, the first candidate that is tested and accepted is the
    # second.  It is kept when stopping right after it.
    rec, m = self.make(lambda d: b"keep" in d,
                       lambda r: r.finishes[-1] == (ACCEPT, False))
    self.assertEqual(m.run_minimizer(), ACCEPT)
    self.assertTrue(m.stop_requested)
    self.assertEqual(rec.finishes, [(REJECT, False), (ACCEPT, False)])
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

    m = rec.mk_min_for_text(self.SRC, rec.min_opts(
          should_stop=should_stop))
    self.assertEqual(m.run_minimizer(), INTERRUPTED)
    self.assertFalse(m.stop_requested)
    self.assertEqual(calls, [])



if __name__ == "__main__":
  unittest.main()


# EOF
