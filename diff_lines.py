# diff_lines.py
"""
diff_lines: compute a unified diff between two lists of lines.
"""

from __future__ import annotations

import difflib
from collections.abc import Iterator


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

  # Each change is (i1, i2, j1, j2), meaning `old[i1:i2]` is replaced
  # by `new[j1:j2]`.
  changes = [(i1 + prefix, i2 + prefix, j1 + prefix, j2 + prefix)
             for tag, i1, i2, j1, j2 in matcher.get_opcodes()
             if tag != "equal"]

  # Group the changes into hunks.  Changes separated by at most twice
  # the context length go in the same hunk, since their context lines
  # would otherwise overlap or abut.
  hunks: list[list[tuple[int, int, int, int]]] = []
  for change in changes:
    if hunks and change[0] - hunks[-1][-1][1] <= 2 * context:
      hunks[-1].append(change)
    else:
      hunks.append([change])

  for hunk in hunks:
    # Lines `old[o1:o2]` and `new[n1:n2]` are covered by this hunk.
    # Outside the changes, the lines of `old` and `new` correspond with
    # a fixed offset.
    first_i1, _, first_j1, _ = hunk[0]
    _, last_i2, _, last_j2 = hunk[-1]
    o1 = max(0, first_i1 - context)
    o2 = min(len(old), last_i2 + context)
    n1 = first_j1 - (first_i1 - o1)
    n2 = last_j2 + (o2 - last_i2)
    yield (b"@@ -" + _format_range(o1, o2) +
           b" +" + _format_range(n1, n2) + b" @@\n")

    pos = o1
    for i1, i2, j1, j2 in hunk:
      for line in old[pos:i1]:
        yield _diff_line(b" ", line)
      yield from _diff_run(b"-", old[i1:i2], b"deleted")
      yield from _diff_run(b"+", new[j1:j2], b"inserted")
      pos = i2
    for line in old[pos:o2]:
      yield _diff_line(b" ", line)


def _format_range(start: int, stop: int) -> bytes:
  """
  Format the 0-based half-open line range [`start`,`stop`) for a hunk
  header.  As is conventional, an empty range is described by the line
  number of the line before it.
  """
  length = stop - start
  first = start + 1 if length > 0 else start
  return b"%d,%d" % (first, length)


def _diff_run(prefix: bytes, lines: list[bytes],
              verb: bytes) -> Iterator[bytes]:
  """
  Yield `lines`, a run of insertions or deletions, each with `prefix`.
  If the run is long, summarize its middle, describing the omitted
  lines with `verb`.
  """
  # A run longer than `2*keep+1` is summarized.  (Summarizing a run of
  # exactly `2*keep+1` lines would not make it shorter.)
  keep = 5
  if len(lines) <= 2 * keep + 1:
    for line in lines:
      yield _diff_line(prefix, line)
    return
  for line in lines[:keep]:
    yield _diff_line(prefix, line)
  yield b"<omitting %d %s lines>\n" % (len(lines) - 2 * keep, verb)
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
