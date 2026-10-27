# smin_token.py
"""
SMToken data structure.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SMToken:
  """
  A contiguous sequence of bytes from the input file.

  The tokens partition the input, so concatenating all of them in order
  yields the original file contents.

  The remaining attributes are computed by the tokenizer, as they depend
  on the language and on the token's context in the file.
  """

  text: bytes

  # Delimiter classification: negative for an opening delimiter,
  # positive for a closing delimiter, and zero for a non-delimiter.
  # Opener -n pairs with closer +n.
  delimiter_kind: int

  # Number of leading spaces and tabs on the line containing the token's
  # first non-whitespace character.  If the token is entirely
  # whitespace, this is computed as if a non-whitespace character were
  # appended to it.
  indentation: int

  # True if there are no non-whitespace characters before the token on
  # that same line.  A token that is entirely whitespace is first on its
  # line if it contains a newline.
  first_on_line: bool


# EOF
