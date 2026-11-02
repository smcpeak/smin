# group_head_body.py
"""
Group the "head" of a construct with its delimited "body".

See structure-deduction-algorithm.txt, phase 4.5.
"""

from __future__ import annotations

from typing import Optional

from build_tree_util import recursively_group_sequences
from smin_token import SMToken
from token_tree import TTNode
from whitespace import (
  count_indentation,
  leading_whitespace,
  only_indentation,
)


def group_head_body(node: TTNode) -> TTNode:
  """
  Perform Phase 4.5, grouping heads with delimited bodies, on the tree
  rooted at `node`.  Return the root of a new tree; the input tree is
  not modified, although the new tree shares its `SMToken` objects.

  The first token under `node` is regarded as the first in the file.
  """
  file_first = next(node.tokens(), None)
  return recursively_group_sequences(
    node, lambda nodes: _group_head_body_sequence(nodes, file_first))


def _group_head_body_sequence(
  nodes: list[TTNode],
  file_first: Optional[SMToken],
) -> list[TTNode]:
  """
  Return a copy of the sibling sequence `nodes` in which every adjacent
  pair of a head and a body, as described in the spec, is grouped.
  `file_first` is the first token in the file, if any.
  """
  result: list[TTNode] = []

  for i, node in enumerate(nodes):
    body_indentation = _body_indentation(node)
    if (body_indentation is not None and
        i > 0 and
        _is_head(nodes[i-1], body_indentation, file_first)):
      # The head is the last node in `result`.  It was not already
      # grouped as a body, since a body is a delimiter group and a head
      # is not.  Checking `nodes[i-1]` rather than `result[-1]` ensures
      # a newly made pair is not then treated as the head of a following
      # body.
      result[-1] = TTNode.make_group([result[-1], node])
    else:
      result.append(node)

  return result


def _body_indentation(node: TTNode) -> Optional[int]:
  """
  If `node` could be a body, return the number of spaces and tabs after
  the line break (LF or CRLF) in its opening delimiter's leading
  whitespace.  Otherwise, return None.
  """
  if not node.delim_group:
    return None

  ws = leading_whitespace(node.first_token().text)
  if ws.startswith(b"\n"):
    indentation = ws[1:]
  elif ws.startswith(b"\r\n"):
    indentation = ws[2:]
  else:
    return None
  if not only_indentation(indentation):
    return None
  return len(indentation)


def _is_head(
  node: TTNode,
  body_indentation: int,
  file_first: Optional[SMToken],
) -> bool:
  """
  True if `node` could be the head for a body whose opening delimiter
  has `body_indentation`.  `file_first` is the first token in the file.
  """
  if node.delim_group:
    return False

  first = node.first_token()
  ws = leading_whitespace(first.text)
  last_newline = ws.rfind(b"\n")
  if last_newline < 0 and first is not file_first:
    return False

  # If there is no newline, `last_newline` is -1, so all of `ws` is
  # counted.
  indentation: int = count_indentation(ws[last_newline+1:])
  return indentation <= body_indentation


# EOF
