# diff_lines.py
"""
diff_lines: compute a unified diff between two lists of lines.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
import difflib


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


def diff_lines(old: list[bytes], new: list[bytes]) -> Iterator[bytes]:
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
  """

  # `SequenceMatcher` is very slow on large inputs with many repeated
  # lines (such as blank lines), but in typical uses, such as logging a
  # minimization step, the change is small and localized.  So, first
  # strip the common prefix and suffix, compare only the lines between
  # them, then form the hunks here, taking context lines from anywhere
  # in `old`.
  context = 3
  limit = min(len(old), len(new))
  prefix = 0
  while prefix < limit and old[prefix] == new[prefix]:
    prefix += 1
  suffix = 0
  while (suffix < limit - prefix and
         old[-1 - suffix] == new[-1 - suffix]):
    suffix += 1
  matcher = difflib.SequenceMatcher(
    None, old[prefix:len(old)-suffix], new[prefix:len(new)-suffix],
    autojunk=False)

  # Copy the data from `matcher` into our own format.
  changes: list[_Change] = [
    _Change(_LineRange(i1 + prefix, i2 + prefix),
            _LineRange(j1 + prefix, j2 + prefix))
    for tag, i1, i2, j1, j2 in matcher.get_opcodes()
    if tag != "equal"
  ]

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
      if change.old.start - prev_change.old.stop <= 2 * context:
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
    # include up to `context` lines of context.
    first:     _Change     = hunk[0]
    last:      _Change     = hunk[-1]
    old_start: int         = max(0, first.old.start - context)
    old_stop:  int         = min(len(old), last.old.stop + context)
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
