# byte_range.py
"""
ByteRange class.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ByteRange:
  """
  Describes a contiguous sequence of bytes.
  """

  # 0-based index of the first byte.
  start: int

  # 0-based index of the byte after the last one.
  stop: int


# EOF
