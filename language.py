# language.py
"""
Language protocol: all of the language-specific knowledge used by the
minimizer.
"""

from __future__ import annotations

from typing import Protocol

from minimizer import BraceGroupFunc, NTReplacementFunc
from tokenizer import Tokenizer


class Language(Protocol):
  """Language-specific components of the minimizer."""

  def make_tokenizer(self) -> Tokenizer:
    """Return a tokenizer for this language."""
    ...

  def get_non_trivial_replacement_func(self) -> NTReplacementFunc:
    """
    Return the function that yields the non-trivial replacement text, if
    any, for a token tree node.
    """
    ...

  def get_brace_group_func(self) -> BraceGroupFunc:
    """
    Return the function that says whether a token tree node is a
    brace-delimited group, for --ma2-brace-groups.
    """
    ...


# EOF
