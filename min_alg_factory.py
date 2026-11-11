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

  kind: MinimizerAlgorithmKind = options.alg_kind()

  if kind == MinimizerAlgorithmKind.MA1:
    return MA1Minimizer(options, tree)

  elif kind == MinimizerAlgorithmKind.MA2:
    return MA2Minimizer(options, tree)

  elif kind == MinimizerAlgorithmKind.HDD:
    return HDDMinimizer(options, tree)

  elif kind == MinimizerAlgorithmKind.MA3:
    return MA3Minimizer(options, tree)

  assert False, f"Unrecognized alg_kind: {kind}"


# EOF
