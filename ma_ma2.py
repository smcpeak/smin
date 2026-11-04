# ma_ma2.py
"""
Minimization algorithm 1 (MA2).
"""

from __future__ import annotations

from ma_kind import MinimizationAlgorithmKind
from minimizer import Minimizer


class MA2Minimizer(Minimizer):
  """
  The basic ideas of MA2 are (1) to put early effort into minimizing
  near the end of the file, and (2) to go depth first, limited by a
  gradually increasing depth limit.

  At the moment, the first half of its first pass is more effective than
  any other algorithm I've tested, but after that it falls off.

  See minimization-algorithm.txt for details.
  """


  def get_ma_kind(self) -> MinimizationAlgorithmKind:
    return MinimizationAlgorithmKind.MA2


  def _total_num_passes(self) -> int:

    # MA2 makes one pass per level of the tree.
    ret: int = self.tree_root.depth()

    if self.max_passes is not None:
      ret = min(ret, self.max_passes)

    return ret


  def _run_specific_minimizer(self) -> None:
    for k in range(self._total_num_passes()):
      self.pass_index = k
      self._ma2_min_node(self.tree_root, k+1)


  def _get_cur_granularity(self) -> float:
    return float(self.ma2_granularity)


# EOF
