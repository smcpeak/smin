# ma_hdd.py
"""
Hierarchical Delta Debugging (HDD) minimization algorithm.

See doc/hdd-algorithm.txt.
"""

from __future__ import annotations

import math

from min_alg_kind import MinimizerAlgorithmKind
from minimizer import Minimizer
from token_tree import TTNode


def compute_candidate_numbers(n: int) -> tuple[int, dict[int, int]]:
  """
  Return Cm (maximum candidate number) for a `_ddmin` pass whose input
  is a list of length `n`, and a map from G (granularity) to the C
  (candidate number) for that iteration's starting candidate number.
  """
  c: int = 0
  c_for_g: dict[int, int] = {}

  # Start G the same way `_ddmin` does.
  g: int = max(1, n // 2)

  while g > 0:
    # Candidate number at the start of the iteration with granularity G.
    c_for_g[g] = c

    # Number of candidates we would test if (1) all were rejected and
    # (2) no non-trivial replacements were tried.
    c += math.ceil(n / g)

    # Reduce the granularity the same way `_ddmin` does.
    g //= 2

  return c, c_for_g


class HDDMinimizer(Minimizer):
  """
  An approximation of Hierarchical Delta Debugging: Make one pass per
  level of the tree, top down, and in each, minimize the flat list of
  all the live nodes at that level.

  See doc/hdd-algorithm.txt for details, including how this differs from
  HDD as defined in its original paper.
  """

  # ---- Progress data ----
  # G: The granularity, in nodes, of the current `_ddmin` iteration.
  hdd_granularity: int = 0

  # C: The number of the current candidate within the current `_ddmin`
  # call.  This is not an integer for a non-trivial replacement.
  hdd_candidate_number: float = 0

  # Cm: The maximum number of candidates in the current `_ddmin` call,
  # ignoring those with non-trivial replacements.
  hdd_max_candidates: int = 0


  def __post_init(self) -> None:
    assert self.options.alg_kind == MinimizerAlgorithmKind.HDD


  def _total_num_passes(self) -> int:

    # This is MAX_DEPTH, since there is one pass per level of the tree,
    # not counting the root.
    ret: int = self.tree_root.depth()

    if self.options.max_passes is not None:
      ret = min(ret, self.options.max_passes)

    return ret


  def _run_specific_minimizer(self) -> None:
    # Start with level 1 rather than 0 because 0 would mean attempting
    # to remove the entire input (the sole root node), which is very
    # unlikely to be accepted.
    level: int = 1

    nodes: list[TTNode] = self._nodes_at_level(self.tree_root, level)

    # Even with no limit on the number of passes, we might stop before
    # reaching the last level, since deep nodes might have been pruned.
    while nodes and level <= self._total_num_passes():
      self.pass_index = level - 1

      # Minimize and prune in one step.
      self._ddmin(nodes)

      level += 1
      nodes = self._nodes_at_level(self.tree_root, level)


  def _nodes_at_level(self, node: TTNode, level: int) -> list[TTNode]:
    """
    Return the live nodes, in left to right order, that are `level`
    levels below `node`, which must itself be live.  Delimiter tokens
    are excluded.
    """

    if level == 0:
      return [node]

    ret: list[TTNode] = []
    for child in self._get_surviving_nondelim_children(node):
      ret.extend(self._nodes_at_level(child, level-1))
    return ret


  def _ddmin(self, nodes: list[TTNode]) -> None:
    """
    Minimize `nodes` using the approximation of the classic delta
    debugging algorithm in the spec: make a single pass at each
    granularity, only trying to remove runs (never reducing to a run).

    The elements of `nodes` do not necessarily have the same parent, and
    those with the same parent are not necessarily contiguous.
    """

    c_for_g: dict[int, int]
    self.hdd_max_candidates, c_for_g = compute_candidate_numbers(len(nodes))

    # We start by trying to delete about half of the input.
    g: int = max(1, len(nodes) // 2)

    while g > 0:
      self.hdd_granularity = g

      survivors: list[TTNode] = [
        n
        for n in nodes
        if id(n) not in self.cur_replacement
      ]

      # Partition into runs of length `g`, the last possibly shorter.
      runs: list[list[TTNode]] = [
        survivors[i : i+g]
        for i in range(0, len(survivors), g)
      ]

      # Work from the last run to the first.
      for offset, run in enumerate(reversed(runs)):
        self.hdd_candidate_number = c_for_g[g] + offset
        if self._try_candidate({id(n): b"" for n in run}, run):
          continue

        if g == 1:
          n: TTNode = run[0]
          replacement = self.options.language.non_trivial_replacement(n)
          if replacement:
            self.hdd_candidate_number += 0.5
            self._try_candidate({id(n): replacement}, [n])

      g //= 2


  def _get_cur_granularity(self) -> float:
    return float(self.hdd_granularity)


  def _get_cur_completion_fraction(self, nodes: list[TTNode]) -> float:
    return self.hdd_candidate_number / self.hdd_max_candidates


# EOF
