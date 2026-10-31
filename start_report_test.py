# start_report_test.py
"""
Unit tests for start_report.
"""

from __future__ import annotations

import unittest

from diff_lines import ByteRange
from start_report import TestStartReport


def make_report(
  sequence_num: int = 1,
  last_accepted_tok_count: int = 1234,
  pass_num: int = 1,
  total_num_passes: int = 11,
  granularity: float = 1234,
  completion_fraction: float = 0,
  removed_tok_count: int = 1234,
  initial_tok_count: int = 1234,
  changed_byte_range: ByteRange = ByteRange(0, 5000),
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
    changed_byte_range=changed_byte_range,
  )


class TestStartReportTest(unittest.TestCase):
  def test_first_report(self) -> None:
    self.assertEqual(
      make_report().to_console_string(),
      "N=000001 S=1234 P=(01/11) G=1234.0 F=00% R=1234 ...")

  def test_progress_string(self) -> None:
    # The same, without the trailing " ...".
    self.assertEqual(
      make_report().to_progress_string(),
      "N=000001 S=1234 P=(01/11) G=1234.0 F=00% R=1234")

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


if __name__ == "__main__":
  unittest.main()


# EOF
