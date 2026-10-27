# group_delimiters.py
"""
Build a token tree from a token sequence by grouping delimiter tokens.

See structure-deduction-algorithm.txt, phase 2.
"""

from __future__ import annotations

from dataclasses import dataclass

from smin_token import SMToken
from token_tree import TTNode


@dataclass
class _Frame:
  """An element of the delimiter stack used by `group_delimiters`."""

  # The opening delimiter, or None for the bottom (root) frame.
  opener: SMToken | None

  # The delimiter kind as a positive number (i.e., this identifes the
  # *closer* kind we expect to match), or 0 for the root frame.
  kind: int

  # Line indentation of the opener.
  indentation: int

  # Nodes that follow the opener so far.
  children: list[TTNode]


def group_delimiters(tokens: list[SMToken]) -> TTNode:
  """
  Perform Phase 2, grouping by delimiters, on `tokens`.  Return the root
  of the resulting token tree.
  """
  stack: list[_Frame] = [_Frame(None, 0, 0, [])]

  for token in tokens:
    kind = token.delimiter_kind

    if kind < 0:
      # Push a new (as yet) unpaired opener.
      stack.append(_Frame(token, -kind, token.indentation, []))
      continue

    target = _find_opener(stack, token) if kind > 0 else None
    if target is None:
      # Not a delimiter, or an unpaired closer.
      stack[-1].children.append(TTNode.make_token(token))
      continue

    # Convert unpaired openers we've chosen to skip into ordinary
    # tokens.
    while len(stack) - 1 > target:
      _pop_unpaired(stack)

    # Pop the opener that matches closer `token`.
    frame = stack.pop()
    assert frame.opener is not None

    # Build a delimiter group for the matched delimiter pair.
    stack[-1].children.append(TTNode.make_group(
      [TTNode.make_token(frame.opener)] +
        frame.children +
        [TTNode.make_token(token)],
      delim_group=True))

  # At EOF, deal with any openers that never got paired.
  while len(stack) > 1:
    _pop_unpaired(stack)

  # Build and return the root node of the tree.
  return TTNode.make_group(stack[0].children)


def _find_opener(stack: list[_Frame], closer: SMToken) -> int | None:
  """
  Return the index in `stack` of the opener that pairs with `closer`, or
  None if there is none.
  """
  kind = closer.delimiter_kind
  if closer.first_on_line:
    found = _search_stack(stack, kind, closer.indentation)
    if found is not None:
      return found

  if stack[-1].kind == kind:
    return len(stack) - 1

  return _search_stack(stack, kind, closer.indentation)


def _search_stack(stack: list[_Frame], kind: int, indentation: int) -> int | None:
  """
  Return the index of the topmost opener in `stack` of `kind` and
  `indentation`, or None if there is none.
  """
  for i in range(len(stack) - 1, 0, -1):
    if stack[i].kind == kind and stack[i].indentation == indentation:
      return i
  return None


def _pop_unpaired(stack: list[_Frame]) -> None:
  """
  Pop the top frame of `stack`, whose opener is unpaired, moving the
  opener and its following nodes into the frame below.
  """
  frame = stack.pop()
  assert frame.opener is not None
  parent = stack[-1].children
  parent.append(TTNode.make_token(frame.opener))
  parent.extend(frame.children)


# EOF
