# start_report.py
"""
TestStartReport class.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from byte_range import ByteRange


@dataclass
class MA3RecMinAR:
  """
  Recursive minimizer activation record.  This is used in progress
  reports to try to give some sense of where the algorithm is.
  """

  # The index of the child being explored in the `rev_nec` list.
  child_index: int

  # Length of `rev_nec`.
  rev_nec_len: int


  def progress_string(self, i: int, nec_width: int) -> str:
    """
    Return the string used to show this activation record in the
    progress report.
    """
    c: int = self.child_index
    n: int = self.rev_nec_len
    return f"C{i}=({c:0{nec_width}d}/{n:0{nec_width}d})"


# TODO: Provide a way to allow algorithm-specific reporting without
# having all of them known to this module.
@dataclass(frozen=True, kw_only=True)
class MA3ReportData:
  """
  Additional progress data reported by MA3.  See
  minimization-algorithm.txt, "MA3 Progress Reporting".
  """

  # M_NEC: max_necessity.
  max_necessity: int

  # ED: exploration_depth.
  exploration_depth: int

  # MAX_EXPLORATION_DEPTH, which determines the width of ED and LVL.
  max_exploration_depth: int

  # Record of each active `ma3_min_subtree` call that is in its loop
  # over necessary children, outermost first.
  activation_records: list[MA3RecMinAR]

  # LVL: level(N) for the current `ma3_min_node(N)`.
  level: int

  # L_NEC: len(necessary(N)) for that N.
  len_necessary: int

  # G: The number of nodes in the candidate.
  granularity: int


  def status_fields(self) -> tuple[list[str], list[str]]:
    """
    Return the fields to print after F, and those to print before R.
    """
    ed_width = len(str(self.max_exploration_depth))
    nec_width = len(str(self.max_necessity))

    before = [
      f"M_NEC={self.max_necessity:03d}",
      f"ED={self.exploration_depth:0{ed_width}d}",
    ]
    before += [
      frame.progress_string(i, nec_width)
      for i, frame in enumerate(self.activation_records)
    ]
    after = [
      f"LVL={self.level:0{ed_width}d}",
      f"L_NEC={self.len_necessary:0{nec_width}d}",
      f"G={self.granularity:03d}",
    ]
    return before, after


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

  # P: Outer loop pass number, starting with 1, and typically ending
  # with `total_num_passes` (although, depending on the algorithm,
  # stopping earlier than that might be possible).
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

  # The range of bytes in the most recently accepted input that were
  # modified to produce the candidate.  This is passed to the test
  # program in the CHANGED_BYTE_RANGE envvar.
  changed_byte_range: ByteRange

  # Additional data when the algorithm is MA3.
  ma3_data: Optional[MA3ReportData] = None


  def to_progress_string(self) -> str:
    """
    Return the progress report text, "N=... S=... <status>".  This is
    passed to the test program in the SMIN_PROGRESS envvar.  See
    minimization-algorithm.txt, "Progress report".
    """

    # Width of a field holding up to `initial_tok_count`.
    tok_width = len(str(self.initial_tok_count))

    # The granularity is printed with one digit after the decimal point.
    #g_width = tok_width + 2

    p_width = len(str(self.total_num_passes))

    # Truncate rather than round, so that a fraction just below 1 does
    # not print as 100.
    f_percent = min(int(self.completion_fraction * 100), 99)

    fields: list[str] = [
      f"P=({self.pass_num:0{p_width}d}/{self.total_num_passes})",
      # G is disabled for now.
      #f"G={self.granularity:0{g_width}.1f}",
      f"F={f_percent:02d}%",
    ]

    if self.ma3_data is not None:
      # See "MA3 Progress Reporting".
      before, after = self.ma3_data.status_fields()
      fields += before + after

    fields.append(f"R={self.removed_tok_count:0{tok_width}d}")
    status = " ".join(fields)

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
