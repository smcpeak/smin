# ma_factory.py
"""
Factory function to create a Minimizer subclass instance.
"""

from __future__ import annotations

from typing import Optional

from ma_hdd import HDDMinimizer
from ma_kind import MinimizationAlgorithmKind
from ma_ma1 import MA1Minimizer
from ma_ma2 import MA2Minimizer
from minimizer import (
  AcceptanceTestFunc,
  BraceGroupFunc,
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
  ma2_brace_group_func: Optional[BraceGroupFunc] = None,
) -> Minimizer:
  """
  Create a Minimizer object.  Uses `alg_kind` to decide which class.

  If `ma2_brace_group_func` is not None, then `alg_kind` must be MA2,
  and the function is used to implement --ma2-brace-groups.
  """

  # Get the arguments except for the algorithm selector and the
  # algorithm-specific options.
  all_args = locals()
  del all_args["alg_kind"]
  del all_args["ma2_brace_group_func"]

  if alg_kind == MinimizationAlgorithmKind.MA2:
    return MA2Minimizer(**all_args, is_brace_group=ma2_brace_group_func)
  assert ma2_brace_group_func is None, "Brace groups option requires MA2."

  # Choose which class to create.
  cls: type[MA1Minimizer | HDDMinimizer]
  if alg_kind == MinimizationAlgorithmKind.MA1:
    cls = MA1Minimizer
  elif alg_kind == MinimizationAlgorithmKind.HDD:
    cls = HDDMinimizer
  else:
    assert False, f"Bad alg_kind: {alg_kind}"

  # Forward the arguments to that constructor.
  return cls(**all_args)


# EOF
