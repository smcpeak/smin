# abstract_range.py
"""
AbstractRange class.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self


@dataclass(frozen=True)
class AbstractRange:
  """
  Describes a contiguous sequence of elements, identified by their
  0-based indices in some larger sequence.

  The kind of element (bytes, lines, etc.) is not specified here.
  Instead, each kind gets its own subclass, which makes the kinds
  distinct static types: a range of one kind cannot be used where
  another is expected, nor combined with one by methods here (which use
  `Self`), nor compared with one for equality.
  """

  # 0-based index of the first element.
  start: int

  # 0-based index of the element after the last one.
  stop: int


  def length(self) -> int:
    """Return the number of elements in the range."""
    return self.stop - self.start

  def union(self, other: Self) -> Self:
    """Return the smallest range containing `self` and `other`."""
    return type(self)(min(self.start, other.start),
                      max(self.stop, other.stop))


# EOF
