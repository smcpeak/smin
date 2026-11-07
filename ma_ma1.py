# ma_ma1.py
"""
Minimization algorithm 1 (MA1).
"""

from __future__ import annotations

from minimizer import Minimizer
from token_tree import TTNode


class MA1Minimizer(Minimizer):
  """
  The basic idea of MA1 is to use an exponentially decreasing
  granularity in *tokens*, and to keep making passes over the tree,
  removing nodes that are approximately the size of the chosen
  granularity.

  See minimization-algorithm.txt for details.
  """


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


  def _exceeds_half_granularity(self, size: int) -> bool:
    """True if `size` > G/2."""
    # G/2 = S / 2**(k+1), so compare using integers.
    return (size << (self.pass_index + 1)) > len(self.tokens)

  def _exceeds_granularity(self, size: int) -> bool:
    """True if `size` > G."""
    return (size << self.pass_index) > len(self.tokens)


  def _minimize_node(self, parent: TTNode) -> None:
    """
    Try to replace the children of `parent`, recursively, scanning them
    from last to first.
    """

    # This can only happen if the root is a token, which the structure
    # deduction algorithm does not produce.
    if parent.token is not None:
      return

    # Range [lo, hi) of children to consider, excluding delimiters.
    children = parent.children
    lo, hi = (1, len(children)-1) if parent.is_delim_group() else (0, len(children))

    # Index in `children` of the next node to process.  It walks the
    # list backwards.
    i = hi - 1

    while i >= lo:
      node = children[i]

      # Skip dead nodes.
      if id(node) in self.cur_replacement:
        i -= 1
        continue

      size = self.node_size(node)

      if self._exceeds_half_granularity(size):
        # Case 1: Try replacing the entire node.
        if not self._try_replace_single(node):
          if self._exceeds_granularity(size):
            # Case 2: Also try replacing its children.
            self._minimize_node(node)
        i -= 1
        continue

      # Case 3: Accumulate a run of small nodes, ending with `node`.
      run = [node]
      run_size = size
      j = i - 1
      while j >= lo:
        prev = children[j]

        # Skip dead nodes.
        if id(prev) not in self.cur_replacement:
          prev_size = self.node_size(prev)

          # Stop accumulating if `prev` is big enough that we want to
          # try removing it in isolation, or if adding it to the run
          # would make that run larger than the current granularity.
          if (self._exceeds_half_granularity(prev_size) or
              self._exceeds_granularity(run_size + prev_size)):
            break

          run.append(prev)
          run_size += prev_size

        j -= 1

      if len(run) == 1:
        self._try_replace_single(node)
      else:
        # When we try removing a run, we only try the trivial
        # replacement of an empty byte sequence.
        self._try_candidate({id(n): b"" for n in run}, run)

      # Continue with the node that stopped the run, if any.
      i = j


  def _try_replace_single(self, node: TTNode) -> bool:
    """
    Try replacing `node` with the empty sequence, then, if that fails,
    with its non-trivial replacement, if any.  Return True if either
    was accepted.
    """
    if self._try_candidate({id(node): b""}, [node]):
      return True

    replacement = self.language.non_trivial_replacement(node)
    if replacement:
      return self._try_candidate({id(node): replacement}, [node])

    return False


  def _get_cur_granularity(self) -> float:
    return len(self.tokens) / (1 << self.pass_index)


# EOF
