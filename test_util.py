# test_util.py
"""
Utilities shared by the unit tests.
"""

from __future__ import annotations

import textwrap

from token_tree import TTNode


def dedent(s: str) -> str:
  """Dedent `s` and remove one leading newline, if present."""
  s = textwrap.dedent(s)
  return s[1:] if s.startswith("\n") else s


def all_groups(node: TTNode) -> list[TTNode]:
  """Return all group nodes under (and including) `node`, in preorder."""
  if node.is_token():
    return []
  groups = [node]
  for child in node.children:
    groups.extend(all_groups(child))
  return groups


def all_nodes(node: TTNode) -> list[TTNode]:
  """Return all nodes under (and including) `node`, in preorder."""
  nodes = [node]
  for child in node.children:
    nodes.extend(all_nodes(child))
  return nodes


# EOF
