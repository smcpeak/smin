# language.py
"""
Language protocol: all of the language-specific knowledge used by the
minimizer.
"""

from __future__ import annotations

from typing import Optional, Protocol

from token_tree import TTNode
from tokenizer import Tokenizer


class Language(Protocol):
  """Language-specific components of the minimizer."""

  def make_tokenizer(self) -> Tokenizer:
    """Return a tokenizer for this language."""
    ...

  def non_trivial_replacement(self, node: TTNode) -> Optional[bytes]:
    """
    Return the non-trivial replacement text, if any, for `node`.

    If this returns None, then the only replacement is the empty byte
    sequence.  If it returns non-None, then *in addition* to replacement
    by the empty sequence, we also consider replacing the node with the
    returned sequence.

    Ensures that the return value, if not None, is not empty.
    """
    ...

  def is_brace_group(self, node: TTNode) -> bool:
    """
    Return True if `node` is a brace-delimited group, for
    --ma2-brace-groups.
    """
    ...


# EOF
