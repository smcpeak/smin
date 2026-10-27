# tokenizer.py
"""
Tokenizer protocol: the language-specific functions used by the
structure deduction algorithm.
"""

from __future__ import annotations

from typing import Protocol

from smin_token import SMToken


class Tokenizer(Protocol):
  """Language-specific tokenization and delimiter classification."""

  def tokenize(self, data: bytes) -> list[SMToken]:
    """
    Partition `data` into tokens.  Whitespace is included with the
    following non-whitespace token, except that whitespace at the end of
    the input may be a token of its own.
    """
    ...

  def delimiter_kind(self, token: SMToken) -> int:
    """
    Classify `token` as a delimiter.  Return a negative number for an
    opening delimiter, a positive number for a closing delimiter, and
    zero for a non-delimiter.  Opener -n pairs with closer +n.
    """
    ...


# EOF
