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
  TestStartReport,
)
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
    self.finishes: list[AcceptanceTestResult] = []

  def test(self, data: bytes) -> AcceptanceTestResult:
    self.tested.append(data)
    if len(self.tested) == self.interrupt_at:
      return INTERRUPTED
    return ACCEPT if self.accept(data) else REJECT

  def make_minimizer(
    self,
    root: TTNode,
    nt: NTReplacementFunc = no_replacement,
  ) -> Minimizer:
    return Minimizer(root, nt, self.test, self.starts.append,
                     self.finishes.append)


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
    self.assertEqual(
      self.render(b"a;\nb;\n", {b"\nb;": b"", b"\n": b""}),
      b"a;")

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
      b"#define A 1\n;")

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


def make_report(
  sequence_num: int = 1,
  last_accepted_tok_count: int = 1234,
  pass_num: int = 1,
  total_num_passes: int = 11,
  granularity: float = 1234,
  completion_fraction: float = 0,
  removed_tok_count: int = 1234,
  initial_tok_count: int = 1234,
) -> TestStartReport:
  """Make a report, with defaults for a 1234-token input."""
  return TestStartReport(
    sequence_num=sequence_num,
    last_accepted_tok_count=last_accepted_tok_count,
    pass_num=pass_num,
    total_num_passes=total_num_passes,
    granularity=granularity,
    completion_fraction=completion_fraction,
    removed_tok_count=removed_tok_count,
    initial_tok_count=initial_tok_count,
  )


class TestStartReportTest(unittest.TestCase):
  def test_first_report(self) -> None:
    self.assertEqual(
      make_report().to_console_string(),
      "N=000001 S=1234 P=(01/11) G=1234.0 F=00% R=1234 ...")

  def test_padding(self) -> None:
    self.assertEqual(
      make_report(sequence_num=42, last_accepted_tok_count=567,
                  pass_num=4, granularity=154.25,
                  completion_fraction=0.5, removed_tok_count=8)
        .to_console_string(),
      "N=000042 S=0567 P=(04/11) G=0154.2 F=50% R=0008 ...")

  def test_wide_fields(self) -> None:
    # N grows beyond 6 digits rather than being truncated.
    self.assertEqual(
      make_report(sequence_num=1234567, pass_num=11,
                  granularity=1234 / 1024, completion_fraction=0.07,
                  removed_tok_count=1)
        .to_console_string(),
      "N=1234567 S=1234 P=(11/11) G=0001.2 F=07% R=0001 ...")

  def test_completion_fraction_capped(self) -> None:
    # Truncation keeps a fraction just below 1 at 99%, and the cap
    # handles a fraction of exactly 1.
    for f in [0.999, 1.0]:
      self.assertIn(" F=99% ",
                    make_report(completion_fraction=f).to_console_string())

  def test_single_token_input(self) -> None:
    self.assertEqual(
      make_report(last_accepted_tok_count=1, total_num_passes=1,
                  granularity=1, removed_tok_count=1,
                  initial_tok_count=1).to_console_string(),
      "N=000001 S=1 P=(1/1) G=1.0 F=00% R=1 ...")


class MinimizerTest(unittest.TestCase):
  def check_reports(self, rec: Recorder, m: Minimizer) -> None:
    """Check the consistency of the reports in `rec`."""
    self.assertEqual(len(rec.starts), len(rec.tested))
    self.assertEqual(len(rec.finishes), len(rec.tested))

    # Memoization means no input is tested twice.
    self.assertEqual(len(set(rec.tested)), len(rec.tested))

    prev: TestStartReport | None = None
    for i, r in enumerate(rec.starts):
      self.assertEqual(r.sequence_num, i + 1)
      self.assertEqual(r.total_num_passes, m.total_num_passes)
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
    self.assertEqual(m.get_minimized_test_input(), b"\nkeep")
    self.assertEqual(m.total_num_passes, 4)
    self.assertEqual(len(rec.tested), 8)
    self.assertEqual(rec.tested[0], b"")
    self.check_reports(rec, m)

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
    self.assertEqual(m.get_minimized_test_input(), b" f();\nkeep")
    self.check_reports(rec, m)

  def test_interrupted(self) -> None:
    rec = Recorder(lambda d: b"keep" in d, interrupt_at=4)
    m = rec.make_minimizer(build_tree(tokenize_cpp(
      b"int a;\nint keep;\nint b;\n")))
    self.assertEqual(m.run_minimizer(), INTERRUPTED)
    self.assertEqual(rec.finishes[-1], INTERRUPTED)
    self.assertEqual(len(rec.tested), 4)

    # The result is the last accepted input, not the interrupted one.
    result = m.get_minimized_test_input()
    self.assertIn(b"keep", result)
    self.assertNotEqual(result, rec.tested[-1])

    # The interrupted outcome is not memoized: the initial input, plus
    # the three completed tests.
    self.assertEqual(len(m.memoized_accept), 4)

  def test_initial_input_memoized(self) -> None:
    rec = Recorder(lambda d: True)
    src = b"a;\nb;\n"
    m = rec.make_minimizer(build_tree(tokenize_cpp(src)))
    self.assertEqual(list(m.memoized_accept.values()), [ACCEPT])
    self.assertEqual(m.render_candidate({}), src)

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


if __name__ == "__main__":
  unittest.main()


# EOF
