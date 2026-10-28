# build_tree_util.py
"""
Utilities shared by the tree-building phases.
"""

from __future__ import annotations

from typing import Callable

from token_tree import TTNode


# This function does not have its own direct unit test.  Instead, the
# tests in `group_lines_test` and `group_indentation_test` thoroughly
# exercise it.
def recursively_group_sequences(
  node: TTNode,
  group_sequence: Callable[[list[TTNode]], list[TTNode]],
) -> TTNode:
  """
  Apply `group_sequence` to every sibling sequence in the tree rooted at
  `node`, bottom up.  Return the root of a new tree; the input tree is
  not modified, although the new tree shares its `SMToken` objects.

  `group_sequence` must return a sequence of nodes whose tokens, in
  order, are the same as those of its input, typically by wrapping some
  subsequences in new groups.

  The delimiters at either end of a delimiter group are excluded from
  the sequence passed to `group_sequence`.
  """

  # Recursion base case: grouping of a leaf token is simply that token.
  if node.token is not None:
    return TTNode.make_token(node.token)

  # Recursively group within children.
  #
  # NOTE: The default Python recursion limit is ~1000, which could quite
  # plausibly be hit here.  Within the larger context of input
  # minimization, creating a tree that deep is unlikely to be helpful,
  # so probably we want to impose our own depth limit (of, say, 100).
  # But I'll wait on doing that since it's unlikely to be an issue in
  # practice.
  #
  children: list[TTNode] = [
    recursively_group_sequences(c, group_sequence) for c in node.children]

  if node.delim_group:
    # The delimiters at either end are not placed into groups.
    children = (
      [children[0]] +
      group_sequence(children[1:-1]) +
      [children[-1]])
  else:
    children = group_sequence(children)

    # If all the children were put into one new group, then that group
    # would be the only child of this one, which is redundant.  For
    # example, this happens in Phase 4 for every line group made by
    # Phase 3, since its first node is first on its line and the rest
    # follow.
    #
    # This does not apply to the interior of a delimiter group, since a
    # group there excludes the delimiters, and hence is not redundant.
    if len(children) == 1 and len(node.children) > 1:
      children = children[0].children

  return TTNode.make_group(children, node.delim_group)


# EOF
