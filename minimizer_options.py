# minimizer_options.py
"""
MinimizerOptions class.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional

from acceptance_test_result import AcceptanceTestResult
from language import Language
from ma_kind import MinimizationAlgorithmKind
from start_report import TestStartReport


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

  # Language-specific knowledge, such as non-trivial (non-empty) node
  # replacements.
  language: Language

  # Optional additional stop condition.
  should_stop: Optional[StopQueryFunc]

  # Function to call just before testing a candidate.
  report_test_starting: TestStartReportFunc

  # Function to call after a candidate test finishes.
  report_test_finished: TestFinishedReportFunc

  # If True, MA2 only considers the children of the root and of "brace
  # groups" (as identified by `language`) as candidates for removal.
  #
  # If this is True, then `alg_kind` must be MA2.
  ma2_brace_groups: bool


  def __post_init__(self) -> None:
    if self.alg_kind != MinimizationAlgorithmKind.MA2:
      assert not self.ma2_brace_groups, (
        "Brace groups option requires MA2.")


# EOF
