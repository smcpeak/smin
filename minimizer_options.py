# minimizer_options.py
"""
MinimizerOptions class.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional

from acceptance_test_result import AcceptanceTestResult
from ma_kind import MinimizationAlgorithmKind
from start_report import TestStartReport
from token_tree import TTNode


# Signature of a function that can specify non-trivial replacement text
# for a node.  If it returns None, then the only replacement is the
# empty byte sequence.  If it returns non-None, then *in addition* to
# replacement by the empty sequence, we also consider replacing the node
# with the specified sequence.
NTReplacementFunc = Callable[[TTNode], Optional[bytes]]


# Signature of a function that returns True if a token tree node is a
# brace-delimited group.
BraceGroupFunc = Callable[[TTNode], bool]


# Signature of a function that checks a candidate input for acceptance
# as "interesting" for minimization purposes.  The second argument is
# the progress report for the candidate.  In normal operation, this
# spawns a new process to run an external program, and waits for it to
# terminate.
AcceptanceTestFunc = Callable[[bytes, TestStartReport], AcceptanceTestResult]


# Signature of a function that accepts a test start report.  In normal
# operation, the callee prints this data to the console.
TestStartReportFunc = Callable[[TestStartReport], None]

# Signature of a function called when a test finishes.  The second
# argument is True if the result came from the memoization table rather
# than running the test.  Again, this is normally just printed to the
# console.
TestFinishedReportFunc = Callable[[AcceptanceTestResult, bool], None]

# Signature of a function called after each candidate is tested (and,
# if accepted, made current).  If it returns True, minimization stops.
# In normal operation, this checks whether a time limit has been
# reached.
StopQueryFunc = Callable[[], bool]


@dataclass(frozen=True, kw_only=True)
class MinimizerOptions:
  """
  Various options that control which minimizer algorithm to use, and the
  details of how that minimizer operates.
  """

  # Which algorithm to use.
  alg_kind: MinimizationAlgorithmKind

  # Optional limit on the number of "passes", i.e., iterations of the
  # outer loop of the minimizer.
  max_passes: Optional[int]

  # Candidate tester.
  #
  # TODO: Combine this with `report_test_*`.
  test_acceptance: AcceptanceTestFunc

  # Language-dependent optional non-trivial (non-empty) node replacement.
  #
  # TODO: Combine with `ma2_brace_group_func`.
  get_non_trivial_replacement: NTReplacementFunc

  # Optional additional stop condition.
  should_stop: Optional[StopQueryFunc]

  # Function to call just before testing a candidate.
  report_test_starting: TestStartReportFunc

  # Function to call after a candidate test finishes.
  report_test_finished: TestFinishedReportFunc

  # Optional language-specific test for whether a node is a "brace
  # group", which is something that MA2 can use.
  #
  # If this is not None, then `alg_kind` must be MA2.
  ma2_brace_group_func: Optional[BraceGroupFunc]


  def __post_init__(self) -> None:
    if self.alg_kind != MinimizationAlgorithmKind.MA2:
      assert self.ma2_brace_group_func is None, (
        "Brace groups option requires MA2.")


# EOF
