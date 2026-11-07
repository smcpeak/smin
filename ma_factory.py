# ma_factory.py
"""
Factory function to create a Minimizer subclass instance.
"""

from __future__ import annotations

from ma_hdd import HDDMinimizer
from min_alg_kind import MinimizationAlgorithmKind
from ma_ma1 import MA1Minimizer
from ma_ma2 import MA2Minimizer
from minimizer import Minimizer
from minimizer_options import MinimizerOptions
from token_tree import TTNode


def make_minimizer(
  tree_root: TTNode,
  options: MinimizerOptions,
) -> Minimizer:
  """
  Create a Minimizer object.  Uses `options` to decide which class.
  """

  # Choose which class to create.
  cls: type[MA1Minimizer | MA2Minimizer | HDDMinimizer]
  if options.alg_kind == MinimizationAlgorithmKind.MA1:
    cls = MA1Minimizer
  elif options.alg_kind == MinimizationAlgorithmKind.MA2:
    cls = MA2Minimizer
  elif options.alg_kind == MinimizationAlgorithmKind.HDD:
    cls = HDDMinimizer
  else:
    assert False, f"Bad alg_kind: {options.alg_kind}"

  # Forward the arguments to that constructor.
  return cls(tree_root, options)


# EOF
