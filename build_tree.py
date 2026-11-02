# build_tree.py
"""
Build a token tree from a token sequence.

See structure-deduction-algorithm.txt.
"""

from __future__ import annotations

from group_delimiters import group_delimiters
from group_indentation import group_indentation
from group_lines import group_lines
from group_paragraphs import group_paragraphs
from smin_token import SMToken
from token_tree import TTNode

import os


def build_tree(tokens: list[SMToken]) -> TTNode:
  """
  Deduce the hierarchical structure of `tokens`, returning the root of
  a tree whose leaves are those tokens, in order.

  This performs phases 2 through 5 of the algorithm.  Phase 6 is not
  needed as a separate pass, since the grouping phases do not create
  redundant groups (see `recursively_group_sequences`).
  """

  # For experimentation, optionally disable paragraphing at top level.
  skip_toplevel: bool = (os.environ.get("SKIP_TOP_PARA", "") == "1")

  return group_paragraphs(
    group_indentation(group_lines(group_delimiters(tokens))),
    skip_toplevel = skip_toplevel)


# EOF
