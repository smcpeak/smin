# acceptance_tester.py
"""
AcceptanceTester class.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from acceptance_test_result import AcceptanceTestResult
from start_report import TestStartReport


class AcceptanceTester(ABC):
  """
  Functions related to testing whether a candidate is acceptable in a
  minimization context.
  """

  @abstractmethod
  def test_acceptance(
    self,
    candidate: bytes,
    start_report: TestStartReport,
  ) -> AcceptanceTestResult:
    """
    Check `candidate` input for acceptance as "interesting" for
    minimization purposes.  `start_report` is the progress report for
    the candidate.  In normal minimizer operation, this spawns a new
    process to run an external program, and waits for it to terminate.
    """
    pass

  def report_test_starting(
    self,
    start_report: TestStartReport,
  ) -> None:
    """
    This is called when a candidate is ready for testing, before
    `test_acceptance` (although that might be skipped if the candidate
    has a memoized result).  In normal operation, the callee prints this
    data to the console.

    The default does nothing.
    """
    pass

  def report_test_finished(
    self,
    result: AcceptanceTestResult,
    memoized: bool,
  ) -> None:
    """
    This is called when a test finishes.  `memoized` is True if the
    result came from the memoization table rather than running the test.
    This information is normally just printed to the console.

    The default does nothing.
    """
    pass


# EOF
