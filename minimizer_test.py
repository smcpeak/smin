# minimizer_test.py
"""
Unit tests for minimizer.
"""

from __future__ import annotations

import unittest
from collections.abc import Callable

from acceptance_test_result import AcceptanceTestResult
from build_tree import build_tree
from minimizer import (
  Minimizer,
  NTReplacementFunc,
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

    # The minimizer made by `make_minimizer`.
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

  def make_minimizer(
    self,
    root: TTNode,
    nt: NTReplacementFunc = no_replacement,
    max_passes: int | None = None,
    ma2: bool = False,
  ) -> Minimizer:
    self.minimizer = Minimizer(root, nt, self.test, self.starts.append,
                               self.finish, max_passes, ma2)
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
    m = Recorder(lambda d: True).make_minimizer(root)
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
    m = Recorder(lambda d: True).make_minimizer(root)
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
      self.assertEqual(r.total_num_passes, m.total_num_passes)
      if m.ma2:
        # The granularity is a number of nodes.
        self.assertEqual(r.granularity, int(r.granularity))
        self.assertGreaterEqual(r.granularity, 1)
      else:
        self.assertEqual(r.granularity,
                         len(m.tokens) / 2 ** (r.pass_num - 1))
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
  def test_empty_input(self) -> None:
    rec = Recorder(lambda d: True)
    m = rec.make_minimizer(build_tree(tokenize_cpp(b"")))
    self.assertEqual(m.run_minimizer(), ACCEPT)
    self.assertEqual(m.get_minimized_test_input(), b"")
    self.assertEqual(rec.tested, [])

  def test_accept_everything(self) -> None:
    # The first candidate removes every child of the root, at which
    # point minimization stops.
    rec = Recorder(lambda d: True)
    m = rec.make_minimizer(build_tree(tokenize_cpp(b"a b c")))
    self.assertEqual(m.run_minimizer(), ACCEPT)
    self.assertEqual(m.get_minimized_test_input(), b"")
    self.assertEqual(rec.tested, [b""])
    self.check_reports(rec, m)

  def test_keep_one_identifier(self) -> None:
    rec = Recorder(lambda d: b"keep" in d)
    m = rec.make_minimizer(build_tree(tokenize_cpp(
      b"int a;\nint keep;\nint b;\n")))
    self.assertEqual(m.run_minimizer(), ACCEPT)
    self.assertEqual(m.get_minimized_test_input(), b"\nkeep\n")
    self.assertEqual(m.total_num_passes, 4)
    self.assertEqual(len(rec.tested), 7)
    self.assertEqual(rec.tested[0], b"\n")
    self.check_reports(rec, m)

  def test_max_passes(self) -> None:
    src = b"int a;\nint keep;\nint b;\n"
    rec = Recorder(lambda d: b"keep" in d)
    m = rec.make_minimizer(build_tree(tokenize_cpp(src)), max_passes=2)
    self.assertEqual(m.total_num_passes, 2)
    self.assertEqual(m.run_minimizer(), ACCEPT)
    self.assertEqual(m.get_minimized_test_input(), b"\nint keep;\n")
    self.assertEqual(max(r.pass_num for r in rec.starts), 2)
    self.check_reports(rec, m)

    # A limit above the usual number of passes has no effect.
    rec = Recorder(lambda d: b"keep" in d)
    m = rec.make_minimizer(build_tree(tokenize_cpp(src)), max_passes=5)
    self.assertEqual(m.total_num_passes, 4)

  def test_non_trivial_replacement(self) -> None:
    # Removing the function body is rejected, but replacing it with ";"
    # is accepted.
    def nt(node: TTNode) -> bytes | None:
      if node.delim_group and node.first_token().text.strip() == b"{":
        return b";"
      return None

    rec = Recorder(lambda d: b"keep" in d and b"f();" in d)
    m = rec.make_minimizer(
      build_tree(tokenize_cpp(b"void f() { x; }\nint keep;\n")), nt)
    self.assertEqual(m.run_minimizer(), ACCEPT)
    self.assertEqual(m.get_minimized_test_input(), b" f();\nkeep\n")
    self.check_reports(rec, m)

  def test_interrupted(self) -> None:
    rec = Recorder(lambda d: b"keep" in d, interrupt_at=4)
    m = rec.make_minimizer(build_tree(tokenize_cpp(
      b"int a;\nint keep;\nint b;\n")))
    self.assertEqual(m.run_minimizer(), INTERRUPTED)
    self.assertEqual(rec.finishes[-1], (INTERRUPTED, False))
    self.assertEqual(len(rec.tested), 4)

    # The result is the last accepted input, not the interrupted one.
    result = m.get_minimized_test_input()
    self.assertIn(b"keep", result)
    self.assertNotEqual(result, rec.tested[-1])

    # The interrupted outcome is not memoized: the initial input, plus
    # the three completed tests.
    self.assertEqual(len(m.memoized_accept), 4)

  def test_memo_hits_reported(self) -> None:
    # Nothing can be removed, so later passes repeat candidates that
    # earlier passes already rejected.  (There is no final newline, since
    # removing that would be accepted, via a memo hit, because the
    # rendering restores it.)
    src = b"a;\nb;\nc;\nd;"
    rec = Recorder(lambda d: d == src)
    m = rec.make_minimizer(build_tree(tokenize_cpp(src)))
    self.assertEqual(m.run_minimizer(), ACCEPT)
    self.check_reports(rec, m)

    memo_results = [r for r, memo in rec.finishes if memo]
    self.assertGreater(len(memo_results), 0)
    self.assertEqual(set(memo_results), {REJECT})
    self.assertEqual(len(rec.starts), len(rec.tested) + len(memo_results))

  def test_initial_input_memoized(self) -> None:
    rec = Recorder(lambda d: True)
    src = b"a;\nb;\n"
    m = rec.make_minimizer(build_tree(tokenize_cpp(src)))
    self.assertEqual(list(m.memoized_accept.values()), [ACCEPT])
    self.assertEqual(m.render_candidate({}), src)

  def test_current_tok_count(self) -> None:
    rec = Recorder(lambda d: True)
    root = build_tree(tokenize_cpp(b"int a;\nint b;\n"))
    m = rec.make_minimizer(root)

    # "int", "a", ";", "\nint", "b", ";", "\n".
    self.assertEqual(m.current_tok_count(), 7)

    # Replace a node by modifying `cur_replacement` directly, as if
    # Ctrl-C interrupted `_commit` before it updated `token_live`.
    m.cur_replacement[id(find_node(root, b"\nint b;"))] = b""
    self.assertEqual(m.current_tok_count(), 4)
    self.assertEqual(m.live_tok_count, 7)

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

    rec = Recorder(accept)
    m = rec.make_minimizer(build_tree(tokenize_cpp(src)))
    self.assertEqual(m.run_minimizer(), ACCEPT)
    result = m.get_minimized_test_input()
    self.assertTrue(accept(result))
    self.assertLess(len(result), len(src) // 4)
    self.check_reports(rec, m)

  def test_run_twice_fails(self) -> None:
    rec = Recorder(lambda d: True)
    m = rec.make_minimizer(build_tree(tokenize_cpp(b"a")))
    m.run_minimizer()
    with self.assertRaises(AssertionError):
      m.run_minimizer()


class MA2Test(ReportCheckingTestCase):
  """Tests of Minimization Algorithm 2."""

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
    m = rec.make_minimizer(build_tree(tokenize_cpp(src)), nt,
                           max_passes, ma2=True)
    self.assertEqual(m.run_minimizer(), ACCEPT)
    self.assertTrue(accept(m.get_minimized_test_input()))
    self.check_reports(rec, m)
    return rec, m

  def test_empty_input(self) -> None:
    rec, m = self.run_ma2(b"", lambda d: True)
    self.assertEqual(m.total_num_passes, 0)
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
    self.assertEqual(m.total_num_passes, 2)
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
    self.assertEqual(m.total_num_passes, 1)
    self.assertEqual(m.get_minimized_test_input(), b"\nint keep;\n")
    self.assertEqual({r.pass_num for r in rec.starts}, {1})

    # A limit above the tree depth has no effect.
    rec, m = self.run_ma2(b"int a;\nint keep;\nint b;\n",
                          lambda d: b"keep" in d, max_passes=5)
    self.assertEqual(m.total_num_passes, 2)
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
    m = rec.make_minimizer(
      build_tree(tokenize_cpp(b"int a;\nint keep;\nint b;\n")), ma2=True)
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
