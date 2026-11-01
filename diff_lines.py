# diff_lines.py
"""
diff_lines: compute a unified diff between two lists of lines.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
import difflib
from typing import Optional


# TODO: Move this into its own module.
@dataclass(frozen=True)
class ByteRange:
  """
  Describes a contiguous sequence of bytes.
  """

  # 0-based index of the first byte.
  start: int

  # 0-based index of the byte after the last one.
  stop: int


@dataclass(frozen=True)
class _LineRange:
  """
  Describes a contiguous sequence of lines.
  """

  # 0-based index of the first line in the range.
  start: int

  # 0-based index of the last-plus-one line in the range.
  stop: int

  def format(self) -> bytes:
    """
    Format this range for a hunk header.  As is conventional, an empty
    range is described by the line number of the line before it.
    """
    length = self.stop - self.start
    first = self.start + 1 if length > 0 else self.start
    return b"%d,%d" % (first, length)


@dataclass(frozen=True)
class _Change:
  """
  One change described in a diff, consisting of a contiguous sequence of
  "old" lines being replaced by a contiguous sequence of "new" lines.
  """

  # Lines removed.
  old: _LineRange

  # Lines added.
  new: _LineRange


def diff_lines(
  old: list[bytes],
  new: list[bytes],
  changed_byte_range: Optional[ByteRange] = None,
) -> Iterator[bytes]:
  """
  Yield the lines of a unified diff from `old` to `new`, with three
  lines of context.

  There are no filename headers.

  Each hunk is preceded by a "hunk header" using the conventional
  format:

    @@ -old_start,old_len +new_start,new_len @@

  where the starts are 1-based line numbers.  (GNU diff will omit a
  length of 1 (for example, when a one-line file is modified), but IMO
  that is surprising and not very useful, so for uniformity this code
  does not do that.)

  Additionally, when a hunk contains a run of more than 11 lines of
  contiguous insertions or deletions, that run is summarized by keeping
  only the leading and trailing 5 lines, and in the middle writing a
  "run summary" line:

    <omitting N (inserted|deleted) lines>

  where N is the number of lines omitted and it says "inserted" for a
  run of added lines and "deleted" otherwise.

  If `changed_byte_range` is provided, it is used to help determine the
  unchanged common prefix and suffix.  Specifically, they are each as
  large as possible without overlapping any byte in the given range.
  This is helpful in cases where the "changed" region is ambiguous and
  we want to ensure that what gets highlighted matches what the
  minimizer was actually focused on.
  """

  # `SequenceMatcher` is very slow on large inputs with many repeated
  # lines (such as blank lines), but in typical uses, such as logging a
  # minimization step, the change is small and localized.  So, first
  # strip the common prefix and suffix, compare only the lines between
  # them, then form the hunks here, taking context lines from anywhere
  # in `old`.

  def get_changes() -> list[_Change]:
    """
    Compute the common prefix and suffix, run the diff algorithm on what
    is between them, and return the resulting changes.
    """

    # Byte offset in `old` that the prefix may not extend past.
    prefix_limit_byte: int

    # Byte offset in `old` that the suffix must not extend before.
    suffix_limit_byte: int

    # Compute `prefix_limit_byte` and `suffix_limit_byte`.
    if changed_byte_range is None:
      prefix_limit_byte = sum(map(len, old))
      suffix_limit_byte = 0
    else:
      prefix_limit_byte = changed_byte_range.start
      suffix_limit_byte = changed_byte_range.stop

    # Maximum allowable sum of `prefix` and `suffix`.
    max_affix_lines: int = min(len(old), len(new))

    # Number of lines in the common prefix.
    prefix_len_lines: int = 0

    # The byte offset in `old` of its end.
    prefix_end_byte: int = 0

    # Compute `prefix_len_bytes` and `prefix_end_byte` by expanding the
    # prefix they denote forward as much as possible.
    while (prefix_len_lines < max_affix_lines and
           old[prefix_len_lines] == new[prefix_len_lines] and
           prefix_end_byte + len(old[prefix_len_lines]) <= prefix_limit_byte):
      prefix_end_byte += len(old[prefix_len_lines])
      prefix_len_lines += 1

    # Number of lines in the common suffix.
    suffix_len_lines: int = 0

    # Byte offset in `old` of its start.
    suffix_start_byte: int = sum(map(len, old))

    # Compute `suffix_len_lines` and `suffix_start_byte` by expanding
    # the suffix they denote backwards as much as possible.
    while (prefix_len_lines + suffix_len_lines < max_affix_lines  and
           old[-1 - suffix_len_lines] == new[-1 - suffix_len_lines] and
           suffix_start_byte - len(old[-1 - suffix_len_lines]) >= suffix_limit_byte):
      suffix_start_byte -= len(old[-1 - suffix_len_lines])
      suffix_len_lines += 1

    # Build a difflib matcher that will compare the parts of the input
    # that are not covered by the common prefix and suffix.
    matcher = difflib.SequenceMatcher(
      isjunk   = None,
      a        = old[prefix_len_lines : len(old)-suffix_len_lines],
      b        = new[prefix_len_lines : len(new)-suffix_len_lines],
      autojunk = False)

    # Run the matching algorithm (by calling `get_opcodes()` for the first
    # time), then copy the data it produces into our own format.
    return [
      _Change(_LineRange(i1 + prefix_len_lines, i2 + prefix_len_lines),
              _LineRange(j1 + prefix_len_lines, j2 + prefix_len_lines))
      for tag, i1, i2, j1, j2 in matcher.get_opcodes()
      if tag != "equal"
    ]

  # Get the diff.  (A nested function is used here in order to create a
  # lexical scope that encapsulates its internal logic.)
  changes: list[_Change] = get_changes()

  # Desired number of unchanged lines of context to emit surrounding
  # each change.
  desired_context_lines = 3

  # A "hunk" is a sequence of changes close enough together that they
  # share the invervening context.
  Hunk = list[_Change]

  # Group the changes into hunks.
  hunks: list[Hunk] = []
  change: _Change
  for change in changes:
    if hunks:
      last_hunk: Hunk = hunks[-1]
      prev_change: _Change = last_hunk[-1]
      if change.old.start - prev_change.old.stop <= 2 * desired_context_lines:
        # Expand the last hunk to include `change` since the trailing
        # context of one overlaps with or touches the leading context of
        # the next.
        hunks[-1].append(change)
        continue

    # Start a new hunk.
    hunks.append([change])

  # Emit the hunks one by one.
  hunk: Hunk
  for hunk in hunks:
    # Let `old_range` be the lines covered by this hunk, expanded to
    # include up to `desired_context_lines` lines of context.
    first:     _Change     = hunk[0]
    last:      _Change     = hunk[-1]
    old_start: int         = max(0, first.old.start - desired_context_lines)
    old_stop:  int         = min(len(old), last.old.stop + desired_context_lines)
    old_range: _LineRange  = _LineRange(old_start, old_stop)

    # Corresponding range in the new data, expanded by the same amount
    # on each end that `old_range` was.
    new_range: _LineRange = _LineRange(
      first.new.start - (first.old.start - old_start),
      last.new.stop + (old_stop - last.old.stop))

    # Emit the hunk header.
    yield (b"@@ -" + old_range.format() +
           b" +" + new_range.format() + b" @@\n")

    # Emit the hunk body.
    pos: int = old_range.start
    for change in hunk:
      # Unchanged lines between the previous change and `change`.
      for line in old[pos:change.old.start]:
        yield _diff_line(b" ", line)

      # Removeed lines.
      yield from _diff_run(b"-", old[change.old.start:change.old.stop],
                           b"deleted")

      # Added lines.
      yield from _diff_run(b"+", new[change.new.start:change.new.stop],
                           b"inserted")

      pos = change.old.stop

    # Unchanged lines at the end of the hunk.
    for line in old[pos:old_range.stop]:
      yield _diff_line(b" ", line)


def _diff_run(
  prefix: bytes,
  lines: list[bytes],
  verb: bytes,
) -> Iterator[bytes]:
  """
  Yield `lines`, a run of insertions or deletions, each with `prefix`.
  If the run is long, summarize its middle, describing the omitted
  lines with `verb`.
  """
  # A run longer than `2*keep+1` is summarized.  (Summarizing a run of
  # exactly `2*keep+1` lines would not make it shorter.)
  keep = 5

  if len(lines) <= 2 * keep + 1:
    # The run is short enough to not summarize.
    for line in lines:
      yield _diff_line(prefix, line)
    return

  # Unsummarized run start.
  for line in lines[:keep]:
    yield _diff_line(prefix, line)

  # Summary.
  yield b"<omitting %d %s lines>\n" % (len(lines) - 2 * keep, verb)

  # Unsummarized run end.
  for line in lines[-keep:]:
    yield _diff_line(prefix, line)


def _diff_line(prefix: bytes, line: bytes) -> bytes:
  """
  Return `line` with `prefix`, marking a missing final newline the way
  the `diff` utility does.
  """
  if line.endswith(b"\n"):
    return prefix + line
  return prefix + line + b"\n\\ No newline at end of file\n"


# EOF
