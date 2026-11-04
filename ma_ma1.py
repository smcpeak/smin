# ma_ma1.py
"""
Minimization algorithm 1 (MA1).
"""

from __future__ import annotations

from minimizer import Minimizer


class MA1Minimizer(Minimizer):
  """
  The basic idea of MA1 is to use an exponentially decreasing
  granularity in *tokens*, and to keep making passes over the tree,
  removing nodes that are approximately the size of the chosen
  granularity.

  See minimization-algorithm.txt for details.
  """


  # TODO: Currently this class has both MA1 and MA2 in it.  Split those
  # apart.

  # TODO: The base class has the meat of both MA1 and MA2.  After
  # splitting this class, move those methods to the appropriate
  # subclass.


  def _total_num_passes(self) -> int:

    ret: int

    if self.use_ma2_alg:
      # MA2 makes one pass per level of the tree.
      ret = self.tree_root.depth()
    else:
      # This is floor(log_2(S))+1 for S > 0, and 0 for S = 0.
      ret = len(self.tokens).bit_length()

    if self.max_passes is not None:
      ret = min(ret, self.max_passes)

    return ret


  def _run_specific_minimizer(self) -> None:
    # For the moment, the algorithms still share an outer loop.
    for k in range(self._total_num_passes()):
      self.pass_index = k
      if self.use_ma2_alg:
        self._ma2_min_node(self.tree_root, k+1)
      else:
        self._minimize_node(self.tree_root)


  def _get_cur_granularity(self) -> float:
    return (
      float(self.ma2_granularity) if self.use_ma2_alg
      else len(self.tokens) / (1 << self.pass_index))


# EOF
