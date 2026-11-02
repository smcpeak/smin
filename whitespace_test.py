# whitespace_test.py
"""
Unit tests for whitespace.
"""

from __future__ import annotations

import unittest

from whitespace import count_indentation, leading_whitespace, only_indentation


class LeadingWhitespaceTest(unittest.TestCase):
  def test_empty(self) -> None:
    self.assertEqual(leading_whitespace(b""), b"")

  def test_none(self) -> None:
    self.assertEqual(leading_whitespace(b"x"), b"")
    self.assertEqual(leading_whitespace(b"x  "), b"")

  def test_some(self) -> None:
    self.assertEqual(leading_whitespace(b"  x"), b"  ")
    self.assertEqual(leading_whitespace(b"\n\tfoo bar"), b"\n\t")

  def test_all_whitespace_bytes(self) -> None:
    ws = b" \t\r\f\v\n"
    self.assertEqual(leading_whitespace(ws + b"x"), ws)

  def test_entirely_whitespace(self) -> None:
    self.assertEqual(leading_whitespace(b"\n\n  "), b"\n\n  ")

  def test_ends_at_first_non_whitespace(self) -> None:
    # A newline after a line splice is not leading whitespace.
    self.assertEqual(leading_whitespace(b" \\\n x"), b" ")

  def test_non_ascii_not_whitespace(self) -> None:
    # Bytes outside ASCII, such as the NBSP in Latin-1 or the start of a
    # UTF-8 sequence, are not whitespace.
    self.assertEqual(leading_whitespace(b" \xa0x"), b" ")
    self.assertEqual(leading_whitespace(b" \xc2\xa0x"), b" ")


class OnlyIndentationTest(unittest.TestCase):
  def test_empty(self) -> None:
    self.assertTrue(only_indentation(b""))

  def test_spaces_and_tabs(self) -> None:
    self.assertTrue(only_indentation(b" "))
    self.assertTrue(only_indentation(b"\t"))
    self.assertTrue(only_indentation(b" \t \t\t"))

  def test_other_whitespace(self) -> None:
    for c in [b"\n", b"\r", b"\f", b"\v"]:
      with self.subTest(c=c):
        self.assertFalse(only_indentation(c))
        self.assertFalse(only_indentation(b"  " + c + b"  "))

  def test_non_whitespace(self) -> None:
    self.assertFalse(only_indentation(b"x"))
    self.assertFalse(only_indentation(b"  x"))


class CountIndentationTest(unittest.TestCase):
  def test_empty(self) -> None:
    self.assertEqual(count_indentation(b""), 0)

  def test_spaces_and_tabs_count_equally(self) -> None:
    self.assertEqual(count_indentation(b"    "), 4)
    self.assertEqual(count_indentation(b"\t\t"), 2)
    self.assertEqual(count_indentation(b" \t \t"), 4)

  def test_other_bytes_not_counted(self) -> None:
    # Bytes are counted wherever they are, not just at the start.
    self.assertEqual(count_indentation(b"\r\f\v\nx"), 0)
    self.assertEqual(count_indentation(b" \f\t\r x"), 3)
    self.assertEqual(count_indentation(b"a b\tc"), 2)


if __name__ == "__main__":
  unittest.main()


# EOF
