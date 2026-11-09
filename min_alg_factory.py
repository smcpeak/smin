# min_alg_factory.py
"""
Factory function to create a Minimizer subclass instance.
"""

from __future__ import annotations

from ma_hdd import HDDMinimizer
from ma_ma1 import MA1Minimizer
from ma_ma2 import MA2Minimizer
from min_alg_kind import MinimizerAlgorithmKind
from minimizer import Minimizer
from minimizer_options import MinimizerOptions
from token_tree import TTNode


def make_minimizer(
  options: MinimizerOptions,
  tree_root: TTNode,
) -> Minimizer:
  """
  Create a Minimizer object.  Uses `options` to decide which class.
  """

  # Choose which class to create.
  cls: type[MA1Minimizer | MA2Minimizer | HDDMinimizer]
  kind: MinimizerAlgorithmKind = options.alg_kind()
  if kind == MinimizerAlgorithmKind.MA1:
    cls = MA1Minimizer
  elif kind == MinimizerAlgorithmKind.MA2:
    cls = MA2Minimizer
  elif kind == MinimizerAlgorithmKind.HDD:
    cls = HDDMinimizer
  else:
    assert False, f"Unrecognized alg_kind: {kind}"

  # Forward the arguments to that constructor.
  return cls(options, tree_root)


# EOF
