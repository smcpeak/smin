# ma_ma1.py
"""
Minimization algorithm 1 (MA1).
"""

from __future__ import annotations

from ma_kind import MinimizationAlgorithmKind
from minimizer import Minimizer


class MA1Minimizer(Minimizer):
  """
  The basic idea of MA1 is to use an exponentially decreasing
  granularity in *tokens*, and to keep making passes over the tree,
  removing nodes that are approximately the size of the chosen
  granularity.

  See minimization-algorithm.txt for details.
  """


  # TODO: The base class has the meat of both MA1 and MA2.  After
  # splitting this class, move those methods to the appropriate
  # subclass.


  def get_ma_kind(self) -> MinimizationAlgorithmKind:
    return MinimizationAlgorithmKind.MA1


  def _total_num_passes(self) -> int:

    # This is floor(log_2(S))+1 for S > 0, and 0 for S = 0.
    ret: int = len(self.tokens).bit_length()

    if self.max_passes is not None:
      ret = min(ret, self.max_passes)

    return ret


  def _run_specific_minimizer(self) -> None:
    for k in range(self._total_num_passes()):
      self.pass_index = k
      self._minimize_node(self.tree_root)


  def _get_cur_granularity(self) -> float:
    return len(self.tokens) / (1 << self.pass_index)


# EOF
