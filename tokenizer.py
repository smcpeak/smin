# tokenizer.py
"""
Tokenizer protocol: the language-specific functions used by the
structure deduction algorithm.
"""

from __future__ import annotations

from typing import Protocol

from smin_token import SMToken


class Tokenizer(Protocol):
  """Language-specific functions used by structure deduction."""

  def tokenize(self, data: bytes) -> list[SMToken]:
    """
    Partition `data` into tokens.  Whitespace is included with the
    following non-whitespace token, except that whitespace at the end of
    the input may be a token of its own.  Every attribute of each token
    is computed, including its delimiter classification.
    """
    ...


# EOF
