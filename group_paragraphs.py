# group_paragraphs.py
"""
Group the nodes of a token tree that make up a paragraph.

See structure-deduction-algorithm.txt, phase 5.
"""

from __future__ import annotations

from build_tree_util import recursively_group_sequences
from smin_token import SMToken
from token_tree import TTNode


# Bytes regarded as whitespace when looking for blank lines.
_WHITESPACE: frozenset[int] = frozenset(b" \t\r\f\v\n")


def group_paragraphs(node: TTNode) -> TTNode:
  """
  Perform Phase 5, grouping paragraphs, on the tree rooted at `node`.
  Return the root of a new tree; the input tree is not modified,
  although the new tree shares its `SMToken` objects.
  """
  return recursively_group_sequences(node, _group_paragraph_sequence)


def _group_paragraph_sequence(nodes: list[TTNode]) -> list[TTNode]:
  """
  Return a copy of the sibling sequence `nodes` in which every maximal
  run of two or more nodes that are all first on their line, have the
  same line indentation, and are not separated by blank lines, is
  grouped.
  """
  result: list[TTNode] = []

  # Nodes in the paragraph currently being accumulated.  Every node in
  # it is first on its line.
  paragraph: list[TTNode] = []

  for node in nodes:
    first = node.first_token()
    if (paragraph and
        first.first_on_line and
        first.indentation == paragraph[0].first_token().indentation and
        not _follows_blank_line(first)):
      paragraph.append(node)
      continue

    _flush(result, paragraph)
    if first.first_on_line:
      paragraph = [node]
    else:
      paragraph = []
      result.append(node)

  _flush(result, paragraph)
  return result


def _flush(result: list[TTNode], paragraph: list[TTNode]) -> None:
  """
  Append the nodes in `paragraph` to `result`, grouped if there are at
  least two.
  """
  if len(paragraph) == 1:
    result.append(paragraph[0])
  elif len(paragraph) > 1:
    result.append(TTNode.make_group(paragraph))


def _follows_blank_line(token: SMToken) -> bool:
  """
  True if the leading whitespace of `token` contains at least two
  newlines, meaning there is a blank line between it and the preceding
  token.

  Leading whitespace ends at the first non-whitespace byte, so a
  newline following a line splice (backslash-newline) is not counted.
  """
  newlines = 0
  for c in token.text:
    if c not in _WHITESPACE:
      break
    if c == 0x0A:
      newlines += 1
      if newlines >= 2:
        return True
  return False


# EOF
