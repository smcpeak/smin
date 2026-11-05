# ma_ma2.py
"""
Minimization algorithm 2 (MA2).
"""

from __future__ import annotations

from ma_kind import MinimizationAlgorithmKind
from minimizer import Minimizer
from token_tree import TTNode


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


  def _ma2_min_node(self, node: TTNode, max_depth: int) -> None:
    """
    Try to replace the children of `node`, working backward from the
    last, and recursing into each child found to be necessary, down to
    `max_depth` levels below `node`.  This is `ma2_min_node` in the
    spec, "Minimization Algorithm 2".
    """

    # This can only happen if the root is a token, which the structure
    # deduction algorithm does not produce, or in a recursive call for a
    # leaf, which has no children anyway.
    if node.token is not None:
      return

    # The surviving children, excluding delimiters.
    children: list[TTNode] = self._get_surviving_nondelim_children(node)

    # Number of children we are currently trying to remove at once.  If
    # `node` is not a delimiter group, removing all of its children is
    # the same as removing `node`, which the caller just tried, so start
    # with half.  Clamp to 1 so a lone surviving child is still tried.
    granularity: int = (
      len(children) if node.delim_group else len(children) // 2)
    granularity = max(1, granularity)

    # Number of children in scope for removal.  Those at or beyond this
    # index in `children` are deemed necessary (for this call).
    limit: int = len(children)

    while limit > 0:
      # Try removing the last `granularity` children in scope.
      self.ma2_granularity = granularity
      run: list[TTNode] = children[limit-granularity : limit]
      if self._try_candidate({id(n): b"" for n in run}, run):
        # Removing `run` worked.  `_try_candidate` marked the nodes as
        # replaced in the tree, but we need to update our local list.
        del children[limit-granularity : limit]

        # Move the limit to reflect the shortened list.
        limit -= granularity

        # Increase the granularity.  If we succeeded at removing
        # something, we might be able to remove in bigger amounts,
        # since, usually, most of text is removable.
        granularity = min(2 * granularity, limit)
        continue

      if granularity > 1:
        # Removing `run` did not work.  Try removing less at once.
        granularity //= 2
        continue

      # We failed to remove `c` by itself (when using a trivial
      # replacement).
      c: TTNode = run[0]

      # Try a non-trivial replacement.
      replacement = self.get_non_trivial_replacement(c)
      if replacement and self._try_candidate({id(c): replacement}, [c]):
        # Keep `granularity` at 1 since `c` required individualized
        # attention, so its neighbor might too.
        del children[limit-1]
        limit -= 1
        continue

      # We could not remove `c`, so we hereby regard it as necessary, at
      # least until we revisit `node` in a later pass.
      limit -= 1

      # Now try to reduce its children before moving to siblings.
      #
      # This is one of the key changes in MA2: In later passes, we
      # persistently try to reduce nodes near the end before moving
      # toward the beginning.  This is because removing even one small
      # piece near the end could unlock many deletions higher up, so
      # it's worth spending more time here.
      if max_depth > 1:
        self._ma2_min_node(c, max_depth-1)


  def _get_cur_granularity(self) -> float:
    return float(self.ma2_granularity)


# EOF
