# group_lines.py
"""
Group the nodes of a token tree that make up a line.

See structure-deduction-algorithm.txt, phase 3.
"""

from __future__ import annotations

from build_tree_util import recursively_group_sequences
from token_tree import TTNode


def group_lines(node: TTNode) -> TTNode:
  """
  Perform Phase 3, grouping lines, on the tree rooted at `node`.  Return
  the root of a new tree; the input tree is not modified, although the
  new tree shares its `SMToken` objects.
  """
  return recursively_group_sequences(node, _group_line_sequence)


def _group_line_sequence(nodes: list[TTNode]) -> list[TTNode]:
  """
  Return a copy of the sibling sequence `nodes` in which every node that
  is first on its line is grouped with the next node that is last on its
  line, along with all nodes in between.

  If the first node is itself last on its line, or no later node is last
  on its line, then no group is made, since a group with one child would
  be redundant.
  """
  result: list[TTNode] = []
  i = 0
  n = len(nodes)

  # Set to false once a search for a line end fails, since every later
  # search would also fail.
  may_find_end = True

  while i < n:
    if may_find_end and nodes[i].first_token().first_on_line:
      end = _find_line_end(nodes, i)
      if end is None:
        may_find_end = False
      elif end > i:
        result.append(TTNode.make_group(nodes[i:end+1]))
        i = end + 1
        continue

    result.append(nodes[i])
    i += 1

  return result


def _find_line_end(nodes: list[TTNode], start: int) -> int | None:
  """
  Return the index of the first node in `nodes`, at or after `start`,
  that is last on its line, or None if there is none.
  """
  for i in range(start, len(nodes)):
    if nodes[i].last_token().last_on_line:
      return i
  return None


# EOF
