# group_indentation.py
"""
Group the nodes of a token tree according to indentation.

See structure-deduction-algorithm.txt, phase 4.
"""

from __future__ import annotations

from dataclasses import dataclass

from token_tree import TTNode


def group_indentation(node: TTNode) -> TTNode:
  """
  Perform Phase 4, grouping by indentation, on the tree rooted at
  `node`.  Return the root of a new tree; the input tree is not modified,
  although the new tree shares its `SMToken` objects.
  """

  # Recursion base case: grouping of a leaf token is simply that token.
  if node.token is not None:
    return TTNode.make_token(node.token)

  # Recursively group within children.  (See the note in `group_lines`
  # about recursion depth.)
  children: list[TTNode] = [group_indentation(c) for c in node.children]

  if node.delim_group:
    # The delimiters at either end are not placed into indentation
    # groups.  In particular, excluding the closer implements the rule
    # that a group ends before the closing delimiter of its parent.
    children = (
      [children[0]] +
      _group_indentation_sequence(children[1:-1]) +
      [children[-1]])
  else:
    children = _group_indentation_sequence(children)

    # If all the children were put into one new group, then that group
    # would be the only child of this one, which is redundant.  This
    # happens for every line group made by Phase 3, since its first node
    # is first on its line and the rest follow.
    if len(children) == 1 and len(node.children) > 1:
      children = children[0].children

  return TTNode.make_group(children, node.delim_group)


@dataclass
class _Frame:
  """An open indentation group, used by `_group_indentation_sequence`."""

  # Line indentation of the group's first node, or -1 for the bottom
  # frame, which holds the result sequence.
  indentation: int

  # Nodes in the group so far.
  children: list[TTNode]


def _group_indentation_sequence(nodes: list[TTNode]) -> list[TTNode]:
  """
  Return a copy of the sibling sequence `nodes` in which every node that
  is first on its line is grouped with all following nodes up to, but
  not including, the next node that is first on its line and has equal
  or less line indentation.  The resulting groups nest.

  A node that would be grouped with no following nodes is left alone,
  since a group with one child would be redundant.
  """

  # Stack of open groups.  Indentation strictly increases from bottom to
  # top.
  stack: list[_Frame] = [_Frame(-1, [])]

  for node in nodes:
    first = node.first_token()
    if first.first_on_line:
      # This node ends every open group whose first node is indented at
      # least as much, and begins a new one.
      while stack[-1].indentation >= first.indentation:
        _close_top(stack)
      stack.append(_Frame(first.indentation, [node]))
    else:
      stack[-1].children.append(node)

  while len(stack) > 1:
    _close_top(stack)
  return stack[0].children


def _close_top(stack: list[_Frame]) -> None:
  """Pop the top frame of `stack`, adding its group to the frame below."""
  frame = stack.pop()
  if len(frame.children) == 1:
    stack[-1].children.append(frame.children[0])
  else:
    stack[-1].children.append(TTNode.make_group(frame.children))


# EOF
