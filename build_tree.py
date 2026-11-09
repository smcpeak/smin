# build_tree.py
"""
Build a token tree from a token sequence.

See structure-deduction-algorithm.txt.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from group_delimiters import group_delimiters
from group_head_body import group_head_body
from group_indentation import group_indentation
from group_lines import group_lines
from group_paragraphs import group_paragraphs
from smin_token import SMToken
from token_tree import TokenTree, TTNode
from whitespace import only_whitespace


@dataclass
class BuildTreeOptions:
  """
  Options to `build_tree`.
  """

  # True to run the `group_paragraphs` pass.
  use_paragraphs: bool = True

  # When grouping paragraphs, if true, do not do so for the top-level
  # forms (i.e., children of the root node).
  skip_top_para: bool = False

  # True to run the `group_head_body` pass.
  use_head_body: bool = True


  def __post_init__(self) -> None:
    # Allow some envvars to adjust the settings for ease of
    # experimentation.

    if os.environ.get("SKIP_PARA", "") == "1":
      self.use_paragraphs = False
      print("Skipping paragraph grouping.")

    if os.environ.get("SKIP_TOP_PARA", "") == "1":
      self.skip_top_para = True
      print("Skipping paragraph grouping for top-level forms.")

    if os.environ.get("SKIP_HEAD_BODY", "") == "1":
      self.use_head_body = False
      print("Skipping head-body grouping.")


def build_tree(
  tokens: list[SMToken],
  options: BuildTreeOptions | None = None,
) -> TokenTree:
  """
  Deduce the hierarchical structure of `tokens`, returning a tree whose
  leaves are those tokens, in order, except that if the last token is
  entirely whitespace, it is instead stored in `eof_ws`.

  This performs phases 2 through 5 (including 4.5) of the algorithm.
  Phase 6 is not needed as a separate pass, since the grouping phases
  do not create redundant groups (see `recursively_group_sequences`).
  """

  if not options:
    options = BuildTreeOptions()

  # Separate the whitespace at EOF, if any, so the grouping phases (and
  # the minimizer) never see it.
  eof_ws: SMToken | None = None
  if tokens and only_whitespace(tokens[-1].text):
    eof_ws = tokens[-1]
    tokens = tokens[:-1]

  root: TTNode

  # Run through all the phases.
  root = group_delimiters(tokens)
  root = group_lines(root)
  root = group_indentation(root)
  if options.use_head_body:
    root = group_head_body(root)
  if options.use_paragraphs:
    root = group_paragraphs(root, skip_toplevel = options.skip_top_para)

  return TokenTree(root, eof_ws)


# EOF
