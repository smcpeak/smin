# whitespace.py
"""
Data and functions related to whitespace recognition in the minimizer.

This module is intended to encapsulate the mostly language independent
whitespace decisions the minimizer makes.  The language-specific
tokenizers do not use it.

It operates on byte sequences rather than strings because the minimizer
does too.
"""

from __future__ import annotations


# All whitespace bytes.
WHITESPACE: frozenset[int] = frozenset(b" \t\r\f\v\n")

# Bytes counted as indentation.
INDENTATION: frozenset[int] = frozenset(b" \t")


def leading_whitespace(text: bytes) -> bytes:
  """
  Return the whitespace at the start of `text`, which ends at its first
  non-whitespace byte (or is all of it).
  """
  for i, c in enumerate(text):
    if c not in WHITESPACE:
      return text[:i]
  return text


def only_indentation(text: bytes) -> bool:
  """
  True if `text` contains only characters that count as indentation.
  """
  return all(c in INDENTATION for c in text)


def count_indentation(text: bytes) -> int:
  """
  Number of bytes in `text` that count as indentation.
  """
  return sum(1 for c in text if c in INDENTATION)


# EOF
