# diff_lines_test.py
"""
Unit tests for diff_lines.
"""

from __future__ import annotations

import unittest

from diff_lines import diff_lines


def diff(old: bytes, new: bytes) -> str:
  """Diff `old` and `new`, split into lines, returning the diff text."""
  return b"".join(diff_lines(old.splitlines(keepends=True),
                             new.splitlines(keepends=True))).decode()


def numbered(start: int, stop: int) -> bytes:
  """The lines "<start>\\n" through "<stop - 1>\\n"."""
  return b"".join(b"%d\n" % i for i in range(start, stop))


class DiffLinesTest(unittest.TestCase):
  def test_no_change(self) -> None:
    self.assertEqual(diff(b"", b""), "")
    self.assertEqual(diff(b"a\nb\n", b"a\nb\n"), "")

  def test_context(self) -> None:
    # The diff has three lines of context, and no header.
    self.assertEqual(
      diff(b"1\n2\n3\n4\nx\n6\n7\n8\n9\n", b"1\n2\n3\n4\n6\n7\n8\n9\n"),
      " 2\n 3\n 4\n-x\n 6\n 7\n 8\n")

  def test_context_at_ends(self) -> None:
    # Context is truncated at the start and end of the input.
    self.assertEqual(diff(b"a\nb\n", b"x\nb\n"), "-a\n+x\n b\n")
    self.assertEqual(diff(b"a\nb\n", b"a\nx\n"), " a\n-b\n+x\n")

  def test_separate_hunks(self) -> None:
    # Changes separated by more than six unchanged lines are in separate
    # hunks, with a "@@" line between them.
    self.assertEqual(
      diff(numbered(1, 11), numbered(2, 10) + b"ten\n"),
      "-1\n 2\n 3\n 4\n"
      "@@\n"
      " 7\n 8\n 9\n-10\n+ten\n")

  def test_merged_hunks(self) -> None:
    # Changes separated by six unchanged lines are in a single hunk.
    self.assertEqual(
      diff(numbered(1, 9), numbered(2, 8) + b"eight\n"),
      "-1\n 2\n 3\n 4\n 5\n 6\n 7\n-8\n+eight\n")

  def test_insert_and_delete_all(self) -> None:
    self.assertEqual(diff(b"", b"a\nb\n"), "+a\n+b\n")
    self.assertEqual(diff(b"a\nb\n", b""), "-a\n-b\n")

  def test_ambiguous_change(self) -> None:
    # The inserted blank line could be aligned anywhere in the run of
    # blank lines, but the hunk still gets three trailing context lines.
    self.assertEqual(
      diff(b"keep\na\n\n\nb\nc\nd\n", b"keep\na\n\n\n\nb\nc\nd\n"),
      " a\n \n \n+\n b\n c\n d\n")

  def test_no_final_newline(self) -> None:
    self.assertEqual(
      diff(b"keep\nx\n", b"keep\nx"),
      " keep\n-x\n+x\n\\ No newline at end of file\n")

  def test_large_repetitive_input(self) -> None:
    # A localized change in a large input with many repeated lines is
    # handled quickly (this would take many seconds without stripping
    # the common prefix and suffix).
    old = b"{\n\n}\n" * 20000
    new = old[:30000] + b"x\n" + old[30000:]
    self.assertEqual(diff(old, new), " {\n \n }\n+x\n {\n \n }\n")


if __name__ == "__main__":
  unittest.main()


# EOF
