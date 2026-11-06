# build_tree.py
"""
Build a token tree from a token sequence.

See structure-deduction-algorithm.txt.
"""

from __future__ import annotations

from group_delimiters import group_delimiters
from group_head_body import group_head_body
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

  This performs phases 2 through 5 (including 4.5) of the algorithm.
  Phase 6 is not needed as a separate pass, since the grouping phases
  do not create redundant groups (see `recursively_group_sequences`).
  """

  # For experimentation, optionally disable paragraphing at top level.
  skip_top_para: bool = (os.environ.get("SKIP_TOP_PARA", "") == "1")

  # Or even the entire phase.
  skip_para: bool = (os.environ.get("SKIP_PARA", "") == "1")

  # Likewise, maybe skip head-body.
  skip_head_body: bool = (os.environ.get("SKIP_HEAD_BODY", "") == "1")

  root: TTNode

  # Run through all the phases.
  root = group_delimiters(tokens)
  root = group_lines(root)
  root = group_indentation(root)

  if skip_head_body:
    print("Skipping head-body grouping.")
  else:
    root = group_head_body(root)

  if not skip_para:
    root = group_paragraphs(root, skip_toplevel=skip_top_para)

  return root


# EOF
