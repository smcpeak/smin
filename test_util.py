# test_util.py
"""
Utilities shared by the unit tests.
"""

from __future__ import annotations

import textwrap
import unittest
from collections.abc import Callable

from token_tree import TTNode


def dedent(s: str) -> str:
  """Dedent `s` and remove one leading newline, if present."""
  s = textwrap.dedent(s)
  return s.removeprefix("\n")


def dedent_enc(s: str) -> bytes:
  """Dedent `s` and return its UTF-8 encoded bytes."""
  return dedent(s).encode()


def all_groups(node: TTNode) -> list[TTNode]:
  """Return all group nodes under (and including) `node`, in preorder."""
  if node.is_token():
    return []
  groups = [node]
  for child in node.children:
    groups.extend(all_groups(child))
  return groups


def delim_group_texts(node: TTNode) -> list[bytes]:
  """Return the text of each delimiter group under `node`, in preorder."""
  return [g.text() for g in all_groups(node) if g.is_delim_group()]


def all_nodes(node: TTNode) -> list[TTNode]:
  """Return all nodes under (and including) `node`, in preorder."""
  nodes = [node]
  for child in node.children:
    nodes.extend(all_nodes(child))
  return nodes


def check_grouping_phase(
  tc: unittest.TestCase,
  data: bytes,
  input_tree: TTNode,
  phase: Callable[[TTNode], TTNode],
  expect: str,
) -> TTNode:
  """
  Using the assertions of `tc`, check that applying the grouping
  `phase` to `input_tree`, which was built from `data` by the earlier
  phases, yields a tree whose debug string is `expect` (dedented).
  Also check the properties every grouping phase must have.  Return the
  tree.
  """
  input_debug = input_tree.to_debug_string()

  tree = phase(input_tree)

  tc.assertEqual(tree.to_debug_string(), dedent(expect))
  tc.assertEqual(tree.text(), data)
  tree.self_check()

  # The input tree is unchanged, and shares no nodes with the output,
  # but the tokens themselves are shared.
  tc.assertEqual(input_tree.to_debug_string(), input_debug)
  input_ids = {id(n) for n in all_nodes(input_tree)}
  tc.assertFalse(any(id(n) in input_ids for n in all_nodes(tree)))
  for t1, t2 in zip(input_tree.tokens(), tree.tokens(), strict=True):
    tc.assertIs(t1, t2)

  # The grouping phases neither create nor destroy delimiter groups.
  tc.assertFalse(tree.is_delim_group())
  tc.assertEqual(delim_group_texts(tree), delim_group_texts(input_tree))

  return tree


# EOF
