# minimizer.py
"""
Minimizer algorithm class.

See minimizer-algorithm.txt.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from token_tree import TTNode


# Signature of a function that can specify non-trivial replacement text
# for a node.  If it returns None, then the only replacement is the
# empty byte sequence.  If it returns non-None, then *in addition* to
# replacement by the empty sequence, we also consider replacing the node
# with the specified sequence.
NTReplacementFunc = Callable[[TTNode], Optional[bytes]]


class AcceptanceTestResult(Enum):
  """Possible results of an acceptance test invocation."""
  ACCEPT = 1
  REJECT = 2
  INTERRUPTED = 3       # Ctrl-C


# Signature of a function that checks a candidate input for acceptance
# as "interesting" for minimization purposes.  In normal operation, this
# spawns a new process to run an external program, and waits for it to
# terminate.
AcceptanceTestFunc = Callable[[bytes], AcceptanceTestResult]


@dataclass(frozen=True)
class TestStartReport:
  """
  Details to report to the user when an acceptance test is starting.
  """

  # The short identifiers like "N" are the names used in the spec.

  # N: Numbering of the invocations during this minimization attempt,
  # starting with 1.
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


# Signature of a function that accepts a test start report.  In normal
# operation, the callee prints this data to the console.
TestStartReportFunc = Callable[[TestStartReport], None]

# Signature of a function called when a test finishes.  Again, this is
# normally just printed to the console.
TestFinishedReportFunc = Callable[[AcceptanceTestResult], None]


class Minimizer:
  """Minimize a token tree w.r.t. a given acceptance test."""

  # ---- Input ----
  # The root of the token tree representing the original input.
  tree_root: TTNode

  # Query for non-trivial replacement text for a node.
  get_non_trivial_replacement: NTReplacementFunc

  # Check if a given candidate is accepted.  In normal operation, this
  # will start a child process.
  test_acceptance: AcceptanceTestFunc

  # ---- Progress ----
  # Called before starting a test.
  report_test_starting: TestStartReportFunc

  # Called when a test finishes.
  report_test_finished: TestFinishedReportFunc

  # ---- Mutable algorithm data ----
  # Map from TTNode (by object identity, not structure) to its
  # replacement text.  Only nodes that have been replaced are present in
  # the map.  When `run_minimizer` terminates, this holds the data
  # needed to construct the final minimized and accepted candidate.
  cur_replacement: dict[TTNode, bytes]

  # Map from the 16-byte MD5 digest of a candidate input to its outcome,
  # for a candidate that has already been tested.  The INTERRUPTED
  # outcome is never stored here.
  memoized_accept: dict[bytes, AcceptanceTestResult]

  # Initially False, this is set to true by `run_minimizer`, and used to
  # check that that function is only invoked once.
  minimizer_invoked: bool


  # TODO: __init__ that accepts the Input and Progress fields, and
  # initializes the algorithm data.  __init__ requires that the
  # acceptance test has already passed on the initial input, so it puts
  # that initial input into `memoized_accept` right away.


  def run_minimizer(self) -> AcceptanceTestResult:
    """
    Run the main minimizer algorithm.

    Requires that `run_minimizer` has not been invoked previously.

    It returns ACCEPT if we reached the end of the algorithm normally,
    and INTERRUPTED otherwise.
    """

    assert not self.minimizer_invoked
    self.minimizer_invoked = True

    # TODO: Implement.
    return AcceptanceTestResult.INTERRUPTED


  def get_minimized_test_input(self) -> bytes:
    """
    Return the most recently accepted test input, i.e., the primary
    output of the minimizer.

    Requires that `run_minimizer` has been invoked.
    """

    assert self.minimizer_invoked

    # TODO: Implement.
    return b""


# EOF
