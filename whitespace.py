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


# All whitespace bytes as a set.
WHITESPACE_BYTES_SET: frozenset[int] = frozenset(b" \t\r\f\v\n")

# Bytes counted as indentation.
INDENTATION_BYTES_SET: frozenset[int] = frozenset(b" \t")

# Byte sequences that can function as line endings.  Naming these does
# not make code smaller, it makes references to these concepts easier to
# find by grepping.
LF_BYTES: bytes = b"\n"
CRLF_BYTES: bytes = b"\r\n"

NEWLINE_BYTE: int = ord(LF_BYTES)


def leading_whitespace(text: bytes) -> bytes:
  """
  Return the whitespace at the start of `text`, which ends at its first
  non-whitespace byte (or is all of it).
  """
  for i, c in enumerate(text):
    if c not in WHITESPACE_BYTES_SET:
      return text[:i]
  return text


def only_indentation(text: bytes) -> bool:
  """
  True if `text` contains only characters that count as indentation.
  """
  return all(c in INDENTATION_BYTES_SET for c in text)


def count_indentation(text: bytes) -> int:
  """
  Number of bytes in `text` that count as indentation.
  """
  return sum(1 for c in text if c in INDENTATION_BYTES_SET)


def contains_newline(text: bytes) -> bool:
  """
  True if `text` contains a newline character.
  """
  return NEWLINE_BYTE in text


def trail_indent(s: bytes) -> bytes:
  """
  Return the last newline in `s` followed by the whitespace that
  immediately follows it, or the empty sequence if `s` has no newline.
  """
  start = s.rfind(b"\n")
  if start < 0:
    return b""
  return leading_whitespace(s[start:])


# EOF
