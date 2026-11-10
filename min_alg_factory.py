# min_alg_factory.py
"""
Factory function to create a Minimizer subclass instance.
"""

from __future__ import annotations

from ma_hdd import HDDMinimizer
from ma_ma1 import MA1Minimizer
from ma_ma2 import MA2Minimizer
from ma_ma3 import MA3Minimizer
from min_alg_kind import MinimizerAlgorithmKind
from minimizer import Minimizer
from minimizer_options import MinimizerOptions
from token_tree import TokenTree


def make_minimizer(
  options: MinimizerOptions,
  tree: TokenTree,
) -> Minimizer:
  """
  Create a Minimizer object.  Uses `options` to decide which class.
  """

  # Choose which class to create.
  #
  # TODO: Change this code to create the minimizer in the obvious way
  # rather than first choosing the class and then later creating it.
  cls: type[MA1Minimizer | MA2Minimizer | HDDMinimizer | MA3Minimizer]
  kind: MinimizerAlgorithmKind = options.alg_kind()
  if kind == MinimizerAlgorithmKind.MA1:
    cls = MA1Minimizer
  elif kind == MinimizerAlgorithmKind.MA2:
    cls = MA2Minimizer
  elif kind == MinimizerAlgorithmKind.HDD:
    cls = HDDMinimizer
  elif kind == MinimizerAlgorithmKind.MA3:
    cls = MA3Minimizer
  else:
    assert False, f"Unrecognized alg_kind: {kind}"

  # Forward the arguments to that constructor.
  return cls(options, tree)


# EOF
