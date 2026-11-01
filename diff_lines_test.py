# diff_lines_test.py
"""
Unit tests for diff_lines.
"""

from __future__ import annotations

import unittest

from byte_range import ByteRange
from diff_lines import diff_lines


def diff(old: bytes, new: bytes,
         changed: ByteRange | None = None) -> str:
  """
  Diff `old` and `new`, split into lines, with changed byte range
  `changed`, returning the diff text.
  """
  return b"".join(diff_lines(old.splitlines(keepends=True),
                             new.splitlines(keepends=True),
                             changed)).decode()


def numbered(start: int, stop: int) -> bytes:
  """The lines "<start>\\n" through "<stop - 1>\\n"."""
  return b"".join(b"%d\n" % i for i in range(start, stop))


class DiffLinesTest(unittest.TestCase):
  def test_no_change(self) -> None:
    self.assertEqual(diff(b"", b""), "")
    self.assertEqual(diff(b"a\nb\n", b"a\nb\n"), "")

  def test_context(self) -> None:
    # The diff has three lines of context, and no filename header.
    self.assertEqual(
      diff(b"1\n2\n3\n4\nx\n6\n7\n8\n9\n", b"1\n2\n3\n4\n6\n7\n8\n9\n"),
      "@@ -2,7 +2,6 @@\n"
      " 2\n 3\n 4\n-x\n 6\n 7\n 8\n")

  def test_context_at_ends(self) -> None:
    # Context is truncated at the start and end of the input.
    self.assertEqual(diff(b"a\nb\n", b"x\nb\n"),
                     "@@ -1,2 +1,2 @@\n-a\n+x\n b\n")
    self.assertEqual(diff(b"a\nb\n", b"a\nx\n"),
                     "@@ -1,2 +1,2 @@\n a\n-b\n+x\n")

  def test_separate_hunks(self) -> None:
    # Changes separated by more than six unchanged lines are in separate
    # hunks, each with its own header.
    self.assertEqual(
      diff(numbered(1, 11), numbered(2, 10) + b"ten\n"),
      "@@ -1,4 +1,3 @@\n"
      "-1\n 2\n 3\n 4\n"
      "@@ -7,4 +6,4 @@\n"
      " 7\n 8\n 9\n-10\n+ten\n")

  def test_merged_hunks(self) -> None:
    # Changes separated by six unchanged lines are in a single hunk.
    self.assertEqual(
      diff(numbered(1, 9), numbered(2, 8) + b"eight\n"),
      "@@ -1,8 +1,7 @@\n"
      "-1\n 2\n 3\n 4\n 5\n 6\n 7\n-8\n+eight\n")

  def test_insert_and_delete_all(self) -> None:
    # An empty range is described by the line number before it.
    self.assertEqual(diff(b"", b"a\nb\n"), "@@ -0,0 +1,2 @@\n+a\n+b\n")
    self.assertEqual(diff(b"a\nb\n", b""), "@@ -1,2 +0,0 @@\n-a\n-b\n")

  def test_empty_range_in_middle(self) -> None:
    self.assertEqual(diff(b"a\nb\n", b"a\nx\nb\n"),
                     "@@ -1,2 +1,3 @@\n a\n+x\n b\n")
    self.assertEqual(diff(numbered(1, 9), numbered(1, 5) + numbered(6, 9)),
                     "@@ -2,7 +2,6 @@\n 2\n 3\n 4\n-5\n 6\n 7\n 8\n")

  def test_ambiguous_change(self) -> None:
    # The inserted blank line could be aligned anywhere in the run of
    # blank lines, but the hunk still gets three trailing context lines.
    self.assertEqual(
      diff(b"keep\na\n\n\nb\nc\nd\n", b"keep\na\n\n\n\nb\nc\nd\n"),
      "@@ -2,6 +2,7 @@\n"
      " a\n \n \n+\n b\n c\n d\n")

  def test_no_final_newline(self) -> None:
    self.assertEqual(
      diff(b"keep\nx\n", b"keep\nx"),
      "@@ -1,2 +1,2 @@\n"
      " keep\n-x\n+x\n\\ No newline at end of file\n")

  def test_run_not_summarized(self) -> None:
    # A run of 11 deleted lines is shown in full.
    self.assertEqual(
      diff(b"a\n" + numbered(1, 12) + b"b\n", b"a\nb\n"),
      "@@ -1,13 +1,2 @@\n"
      " a\n" +
      "".join(f"-{i}\n" for i in range(1, 12)) +
      " b\n")

  def test_deleted_run_summarized(self) -> None:
    # A run of 12 deleted lines keeps its first and last five lines.
    # The header still describes all of the lines.
    self.assertEqual(
      diff(b"a\n" + numbered(1, 13) + b"b\n", b"a\nb\n"),
      "@@ -1,14 +1,2 @@\n"
      " a\n"
      "-1\n-2\n-3\n-4\n-5\n"
      "<omitting 2 deleted lines>\n"
      "-8\n-9\n-10\n-11\n-12\n"
      " b\n")

  def test_inserted_run_summarized(self) -> None:
    # The final line of the run is kept, along with its newline marker.
    self.assertEqual(
      diff(b"a\n", b"a\n" + numbered(1, 20) + b"20"),
      "@@ -1,1 +1,21 @@\n"
      " a\n"
      "+1\n+2\n+3\n+4\n+5\n"
      "<omitting 10 inserted lines>\n"
      "+16\n+17\n+18\n+19\n+20\n"
      "\\ No newline at end of file\n")

  def test_replaced_runs_summarized(self) -> None:
    # In a replacement, the deleted and inserted runs are summarized
    # separately, and only if long.
    self.assertEqual(
      diff(numbered(1, 14), b"x\n" * 3),
      "@@ -1,13 +1,3 @@\n"
      "-1\n-2\n-3\n-4\n-5\n"
      "<omitting 3 deleted lines>\n"
      "-9\n-10\n-11\n-12\n-13\n"
      "+x\n+x\n+x\n")

  def test_changed_byte_range(self) -> None:
    # Deleting either "a\nb\n" yields the same result.  By default the
    # common prefix is as long as possible, so the second is shown as
    # deleted, but the range can specify that it was the first.
    old = b"a\nb\na\nb\nc\n"
    new = b"a\nb\nc\n"
    self.assertEqual(diff(old, new),
                     "@@ -1,5 +1,3 @@\n a\n b\n-a\n-b\n c\n")
    self.assertEqual(diff(old, new, ByteRange(0, 4)),
                     "@@ -1,5 +1,3 @@\n-a\n-b\n a\n b\n c\n")
    self.assertEqual(diff(old, new, ByteRange(4, 8)),
                     "@@ -1,5 +1,3 @@\n a\n b\n-a\n-b\n c\n")

  def test_changed_byte_range_within_line(self) -> None:
    # A line that overlaps the range is in neither the prefix nor the
    # suffix, even if it is unchanged.  Here, the "b\n" being deleted
    # could be either of them, and the range says it is the second.
    old = b"a\nb\nb\nc\n"
    new = b"a\nb\nc\n"
    self.assertEqual(diff(old, new, ByteRange(4, 5)),
                     "@@ -1,4 +1,3 @@\n a\n b\n-b\n c\n")
    self.assertEqual(diff(old, new, ByteRange(3, 4)),
                     "@@ -1,4 +1,3 @@\n a\n-b\n b\n c\n")

  def test_changed_byte_range_empty(self) -> None:
    # An empty range says where an insertion was made.
    old = b"a\n"
    new = b"a\na\n"
    self.assertEqual(diff(old, new, ByteRange(0, 0)),
                     "@@ -1,1 +1,2 @@\n+a\n a\n")
    self.assertEqual(diff(old, new, ByteRange(2, 2)),
                     "@@ -1,1 +1,2 @@\n a\n+a\n")

  def test_large_repetitive_input(self) -> None:
    # A localized change in a large input with many repeated lines is
    # handled quickly (this would take many seconds without stripping
    # the common prefix and suffix).
    old = b"{\n\n}\n" * 20000
    new = old[:30000] + b"x\n" + old[30000:]
    self.assertEqual(diff(old, new),
                     "@@ -17998,6 +17998,7 @@\n"
                     " {\n \n }\n+x\n {\n \n }\n")


if __name__ == "__main__":
  unittest.main()


# EOF
