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
  """

  text: bytes


# EOF
