# string_util_test.py
"""
Unit tests for string_util.
"""

from __future__ import annotations

import unittest

from string_util import quote_bytes


class QuoteBytesTest(unittest.TestCase):
  def test_empty(self) -> None:
    self.assertEqual(quote_bytes(b""), '""')

  def test_printable(self) -> None:
    self.assertEqual(quote_bytes(b"int main() {}"), '"int main() {}"')

  def test_printable_boundaries(self) -> None:
    # Space (0x20) and tilde (0x7E) are the ends of the printable range.
    self.assertEqual(quote_bytes(b" ~"), '" ~"')

  def test_simple_escapes(self) -> None:
    self.assertEqual(quote_bytes(b"\n"), r'"\n"')
    self.assertEqual(quote_bytes(b"\t"), r'"\t"')
    self.assertEqual(quote_bytes(b"\r"), r'"\r"')
    self.assertEqual(quote_bytes(b'"'), r'"\""')
    self.assertEqual(quote_bytes(b"\\"), r'"\\"')

  def test_single_quote_not_escaped(self) -> None:
    self.assertEqual(quote_bytes(b"'"), "\"'\"")

  def test_octal_escapes(self) -> None:
    self.assertEqual(quote_bytes(b"\x00"), r'"\000"')
    self.assertEqual(quote_bytes(b"\x1f"), r'"\037"')
    self.assertEqual(quote_bytes(b"\x7f"), r'"\177"')
    self.assertEqual(quote_bytes(b"\x80"), r'"\200"')
    self.assertEqual(quote_bytes(b"\xff"), r'"\377"')

  def test_octal_escape_followed_by_digit(self) -> None:
    # The escape is always three digits, so a following digit is not
    # absorbed into it.
    self.assertEqual(quote_bytes(b"\x01" b"7"), r'"\0017"')

  def test_utf8_is_escaped_bytewise(self) -> None:
    self.assertEqual(quote_bytes("é".encode("utf-8")), r'"\303\251"')

  def test_mixed(self) -> None:
    self.assertEqual(
      quote_bytes(b'\n  printf("%d\\n", x);\x01'),
      r'"\n  printf(\"%d\\n\", x);\001"')


if __name__ == "__main__":
  unittest.main()


# EOF
