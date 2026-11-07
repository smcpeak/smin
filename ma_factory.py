# ma_factory.py
"""
Factory function to create a Minimizer subclass instance.
"""

from __future__ import annotations

from ma_hdd import HDDMinimizer
from ma_kind import MinimizationAlgorithmKind
from ma_ma1 import MA1Minimizer
from ma_ma2 import MA2Minimizer
from minimizer import Minimizer
from minimizer_options import MinimizerOptions
from token_tree import TTNode


def make_minimizer(
  tree_root: TTNode,
  opt: MinimizerOptions,
) -> Minimizer:
  """
  Create a Minimizer object.  Uses `opt` to decide which class.
  """

  # Get the arguments to relay to the Minimizer constructor.
  #
  # TODO: This is ugly.
  all_args = vars(opt).copy()
  del all_args["alg_kind"]
  del all_args["ma2_brace_groups"]

  if opt.alg_kind == MinimizationAlgorithmKind.MA2:
    return MA2Minimizer(
      tree_root        = tree_root,
      **all_args,
      ma2_brace_groups = opt.ma2_brace_groups)

  # Choose which class to create.
  cls: type[MA1Minimizer | HDDMinimizer]
  if opt.alg_kind == MinimizationAlgorithmKind.MA1:
    cls = MA1Minimizer
  elif opt.alg_kind == MinimizationAlgorithmKind.HDD:
    cls = HDDMinimizer
  else:
    assert False, f"Bad alg_kind: {opt.alg_kind}"

  # Forward the arguments to that constructor.
  return cls(tree_root=tree_root, **all_args)


# EOF
