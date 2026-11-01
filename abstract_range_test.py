# abstract_range_test.py
"""
Unit tests for abstract_range.

Besides testing the behavior of AbstractRange, this demonstrates that
its subclasses are distinct static types.  Code that mypy rejects is
commented out, preceded by the error mypy reports for it.  To see an
error, uncomment the code and run mypy.
"""

from __future__ import annotations

import dataclasses
import unittest
from typing import Any, cast

from abstract_range import AbstractRange


class AppleRange(AbstractRange):
  """A range of apples."""


class OrangeRange(AbstractRange):
  """A range of oranges."""


def count_apples(r: AppleRange) -> int:
  """Accepts only a range of apples."""
  return r.length()


def count_anything(r: AbstractRange) -> int:
  """Accepts a range of any kind."""
  return r.length()


class AbstractRangeTest(unittest.TestCase):
  def test_fields(self) -> None:
    r = AppleRange(2, 5)
    self.assertEqual(r.start, 2)
    self.assertEqual(r.stop, 5)
    self.assertEqual(r.length(), 3)
    self.assertEqual(AppleRange(4, 4).length(), 0)

  def test_repr(self) -> None:
    # The dataclass-generated repr uses the subclass name.
    self.assertEqual(repr(AppleRange(2, 5)), "AppleRange(start=2, stop=5)")

  def test_direct_creation(self) -> None:
    # AbstractRange itself can be instantiated.
    r = AbstractRange(1, 3)
    self.assertEqual(r.length(), 2)
    self.assertIs(type(r.union(AbstractRange(5, 6))), AbstractRange)

  def test_union(self) -> None:
    u = AppleRange(2, 5).union(AppleRange(4, 9))
    self.assertEqual(u, AppleRange(2, 9))

    # The result has the same type as the operands, both statically
    # (by virtue of `Self`) and at run time.
    u2: AppleRange = u
    self.assertIs(type(u2), AppleRange)

  def test_frozen(self) -> None:
    r = AppleRange(2, 5)
    with self.assertRaises(dataclasses.FrozenInstanceError):
      # Use `setattr` with a non-literal name so that mypy does not see
      # the assignment.
      name = "start"
      setattr(r, name, 0)

    # error: Property "start" defined in "AbstractRange" is read-only
    # [misc]
    #r.start = 0

  def test_not_interchangeable_as_arguments(self) -> None:
    apples = AppleRange(0, 4)
    oranges = OrangeRange(0, 4)
    self.assertEqual(count_apples(apples), 4)

    # error: Argument 1 to "count_apples" has incompatible type
    # "OrangeRange"; expected "AppleRange"  [arg-type]
    #count_apples(oranges)

    # The base class is not substitutable for a subclass either.
    #
    # error: Argument 1 to "count_apples" has incompatible type
    # "AbstractRange"; expected "AppleRange"  [arg-type]
    #count_apples(AbstractRange(0, 4))

    # But a function that accepts the base class accepts any kind.
    self.assertEqual(count_anything(apples), 4)
    self.assertEqual(count_anything(oranges), 4)

  def test_not_interchangeable_in_methods(self) -> None:
    apples = AppleRange(0, 4)
    oranges = OrangeRange(2, 6)

    # error: Argument 1 to "union" of "AbstractRange" has incompatible
    # type "OrangeRange"; expected "AppleRange"  [arg-type]
    #apples.union(oranges)

    # error: Incompatible types in assignment (expression has type
    # "AppleRange", variable has type "OrangeRange")  [assignment]
    #wrong: OrangeRange = apples.union(apples)

    # At run time, `union` does not check the type of its argument, so
    # the first mistake above would go unnoticed.  (The cast hides it
    # from mypy.)
    self.assertEqual(apples.union(cast(Any, oranges)), AppleRange(0, 6))

  def test_not_interchangeable_in_equality(self) -> None:
    apples = AppleRange(0, 4)
    oranges = OrangeRange(0, 4)

    # Ranges of different kinds are never equal at run time, since the
    # dataclass-generated `__eq__` requires the same class.  (Using
    # `assertNotEqual` avoids the mypy error below.)
    self.assertNotEqual(apples, oranges)
    self.assertNotEqual(apples, AbstractRange(0, 4))
    self.assertEqual(apples, AppleRange(0, 4))

    # With --strict, mypy also flags the comparison:
    #
    # error: Non-overlapping equality check (left operand type:
    # "AppleRange", right operand type: "OrangeRange")
    # [comparison-overlap]
    #self.assertFalse(apples == oranges)


if __name__ == "__main__":
  unittest.main()


# EOF
