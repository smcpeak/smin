# ma_factory.py
"""
Factory function to create a Minimizer subclass instance.
"""

from __future__ import annotations

from typing import Optional

from ma_kind import MinimizationAlgorithmKind
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
  alg_kind: MinimizationAlgorithmKind,
  tree_root: TTNode,
  max_passes: Optional[int] = None,
  test_acceptance: AcceptanceTestFunc,
  get_non_trivial_replacement: NTReplacementFunc,
  should_stop: Optional[StopQueryFunc] = None,
  report_test_starting: TestStartReportFunc,
  report_test_finished: TestFinishedReportFunc,
) -> Minimizer:
  """
  Create a Minimizer object.  Uses `alg_kind` to decide which class.
  """

  # Get the arguments except for the algorithm selector.
  all_args = locals()
  del all_args["alg_kind"]

  # Choose which class to create.
  cls: type[MA1Minimizer | MA2Minimizer]
  if alg_kind == MinimizationAlgorithmKind.MA1:
    cls = MA1Minimizer
  elif alg_kind == MinimizationAlgorithmKind.MA2:
    cls = MA2Minimizer
  else:
    assert False, f"Bad alg_kind: {alg_kind}"

  # Forward the arguments to that constructor.
  return cls(**all_args)


# EOF
