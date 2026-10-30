# start_report.py
"""
TestStartReport class.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TestStartReport:
  """
  Details to report to the user when an acceptance test is starting.
  """

  # The short identifiers like "N" are the names used in the spec.

  # N: Numbering of the candidates reported during this minimization
  # attempt, starting with 1.  This includes candidates whose verdict
  # was found in the memoization table.
  sequence_num: int

  # S: Number of live tokens in the most recently accepted input.
  last_accepted_tok_count: int

  # P: Outer loop pass number, starting with 1, and ending with
  # `total_num_passes`.
  pass_num: int

  # Pm: The total number of passes we expect to perform.
  total_num_passes: int

  # G: Current granularity, in tokens.  The algorithm is (mainly) trying
  # to remove nodes of about this size.
  granularity: float

  # F: Estimate of how far we are through the current pass, in [0,1].
  completion_fraction: float

  # R: Number of live tokens that were removed to create the current
  # candidate.  That candidate's size (in tokens) can be calculated as
  # `last_accepted_tok_count - removed_tok_count`.
  removed_tok_count: int

  # Number of tokens in the initial input.  This is the maximum value of
  # S, G, and R, so it determines how wide their fields are.
  initial_tok_count: int


  def to_progress_string(self) -> str:
    """
    Return the progress report text, "N=... S=... <status>".  This is
    passed to the test program in the SMIN_PROGRESS envvar.  See
    minimization-algorithm.txt, "Progress report".
    """

    # Width of a field holding up to `initial_tok_count`.
    tok_width = len(str(self.initial_tok_count))

    # The granularity is printed with one digit after the decimal point.
    g_width = tok_width + 2

    p_width = len(str(self.total_num_passes))

    # Truncate rather than round, so that a fraction just below 1 does
    # not print as 100.
    f_percent = min(int(self.completion_fraction * 100), 99)

    status = (
      f"P=({self.pass_num:0{p_width}d}/{self.total_num_passes}) "
      f"G={self.granularity:0{g_width}.1f} "
      f"F={f_percent:02d}% "
      f"R={self.removed_tok_count:0{tok_width}d}")

    return (
      f"N={self.sequence_num:06d} "
      f"S={self.last_accepted_tok_count:0{tok_width}d} "
      f"{status}")

  def to_console_string(self) -> str:
    """
    Return the line to print to the console before the test starts,
    without a trailing newline.
    """
    return self.to_progress_string() + " ..."


# EOF
