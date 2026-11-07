# ma_ma1_test.py
"""
Unit tests for ma_ma1 (Minimization Algorithm 1).
"""

from __future__ import annotations

import unittest

from lang_cpp import CPPLanguage
from minimizer_test import (
  ACCEPT,
  INTERRUPTED,
  Recorder,
  ReportCheckingTestCase,
)


class MA1Test(ReportCheckingTestCase):
  """Tests of Minimization Algorithm 1."""

  def test_accept_everything(self) -> None:
    # The first candidate removes every child of the root, at which
    # point minimization stops.
    rec = Recorder(lambda d: True)
    m = rec.mk_min_for_text(b"a b c")
    self.assertEqual(m.run_minimizer(), ACCEPT)
    self.assertEqual(m.get_minimized_test_input(), b"")
    self.assertEqual(rec.tested, [b""])
    self.check_reports(rec, m)

  def test_keep_one_identifier(self) -> None:
    rec = Recorder(lambda d: b"keep" in d)
    m = rec.mk_min_for_text(b"int a;\nint keep;\nint b;\n")
    self.assertEqual(m.run_minimizer(), ACCEPT)
    self.assertEqual(m.get_minimized_test_input(), b"\nkeep\n")
    self.assertEqual(m._total_num_passes(), 4)
    self.assertEqual(len(rec.tested), 7)
    self.assertEqual(rec.tested[0], b"\n")
    self.check_reports(rec, m)

  def test_max_passes(self) -> None:
    src = b"int a;\nint keep;\nint b;\n"
    rec = Recorder(lambda d: b"keep" in d)
    m = rec.mk_min_for_text(src, rec.min_opts(max_passes=2))
    self.assertEqual(m._total_num_passes(), 2)
    self.assertEqual(m.run_minimizer(), ACCEPT)
    self.assertEqual(m.get_minimized_test_input(), b"\nint keep;\n")
    self.assertEqual(max(r.pass_num for r in rec.starts), 2)
    self.check_reports(rec, m)

    # A limit above the usual number of passes has no effect.
    rec = Recorder(lambda d: b"keep" in d)
    m = rec.mk_min_for_text(src, rec.min_opts(max_passes=5))
    self.assertEqual(m._total_num_passes(), 4)

  def test_non_trivial_replacement(self) -> None:
    # Removing the function body is rejected, but replacing it with ";"
    # is accepted.
    rec = Recorder(lambda d: b"keep" in d and b"f();" in d)
    m = rec.mk_min_for_text(
      b"void f() { x; }\nint keep;\n",
      rec.min_opts(language=CPPLanguage()))
    self.assertEqual(m.run_minimizer(), ACCEPT)
    self.assertEqual(m.get_minimized_test_input(), b" f();\nkeep\n")
    self.check_reports(rec, m)

  def test_interrupted(self) -> None:
    rec = Recorder(lambda d: b"keep" in d, interrupt_at=4)
    m = rec.mk_min_for_text(b"int a;\nint keep;\nint b;\n")
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
    m = rec.mk_min_for_text(src)
    self.assertEqual(m.run_minimizer(), ACCEPT)
    result = m.get_minimized_test_input()
    self.assertTrue(accept(result))
    self.assertLess(len(result), len(src) // 4)
    self.check_reports(rec, m)


if __name__ == "__main__":
  unittest.main()


# EOF
