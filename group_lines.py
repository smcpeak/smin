# group_lines.py
"""
Group the nodes of a token tree that make up a line.

See structure-deduction-algorithm.txt, phase 3.
"""

from __future__ import annotations

from token_tree import TTNode


def group_lines(node: TTNode) -> TTNode:
  """
  Perform Phase 3, grouping lines, on the tree rooted at `node`.  Return
  the root of a new tree; the input tree is not modified, although the
  new tree shares its `SMToken` objects.
  """

  # Recursion base case: grouping of a leaf token is simply that token.
  if node.token is not None:
    return TTNode.make_token(node.token)

  # Recursively group lines within children.
  #
  # NOTE: The default Python recursion limit is ~1000, which could quite
  # plausibly be hit here.  Within the larger context of input
  # minimization, creating a tree that deep is unlikely to be helpful,
  # so probably we want to impose our own depth limit (of, say, 100).
  # But I'll wait on doing that since it's unlikely to be an issue in
  # practice.
  #
  children: list[TTNode] = [group_lines(child) for child in node.children]

  if node.delim_group:
    # The delimiters at either end are not placed into line groups.
    children = (
      [children[0]] +
      _group_line_sequence(children[1:-1]) +
      [children[-1]])
  else:
    children = _group_line_sequence(children)

  return TTNode.make_group(children, node.delim_group)


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
