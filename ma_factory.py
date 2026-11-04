# ma_factory.py
"""
Factory function to create a Minimizer subclass instance.
"""

from __future__ import annotations

from typing import Optional

from ma_ma1 import MA1Minimizer
from ma_ma2 import MA2Minimizer
from minimizer import (
  AcceptanceTestFunc,
  Minimizer,
  NTReplacementFunc,
  StopQueryFunc,
  TestStartReportFunc,
  TestFinishedReportFunc,
)
from token_tree import TTNode


def make_minimizer(
  *,
  use_ma2_alg: bool = False,
  tree_root: TTNode,
  max_passes: Optional[int] = None,
  test_acceptance: AcceptanceTestFunc,
  get_non_trivial_replacement: NTReplacementFunc,
  should_stop: Optional[StopQueryFunc] = None,
  report_test_starting: TestStartReportFunc,
  report_test_finished: TestFinishedReportFunc,
) -> Minimizer:
  """
  Create a Minimizer object.  Uses `use_ma2_alg` to decide which class.
  """
  # TODO: Generalize the boolean to allow more than two algorithms.

  # Get the arguments except for the algorithm selector.
  all_args = locals()
  del all_args["use_ma2_alg"]

  # Choose which class to create.
  cls = MA2Minimizer if use_ma2_alg else MA1Minimizer

  # Forward the arguments to that constructor.
  return cls(**all_args)


# EOF
