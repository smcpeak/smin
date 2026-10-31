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
  lines of context, but without the file header or the line numbers of
  each hunk.  Hunks after the first are preceded by a "@@" line.
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

  for n, (i1, i2, j1, j2) in enumerate(changes):
    if n == 0 or i1 - changes[n-1][1] > 2 * context:
      # Start a new hunk.
      if n > 0:
        yield b"@@\n"
      unchanged = old[max(0, i1 - context):i1]
    else:
      # Continue the current hunk.
      unchanged = old[changes[n-1][1]:i1]
    for line in unchanged:
      yield _diff_line(b" ", line)
    for line in old[i1:i2]:
      yield _diff_line(b"-", line)
    for line in new[j1:j2]:
      yield _diff_line(b"+", line)
    if n == len(changes) - 1 or changes[n+1][0] - i2 > 2 * context:
      # End the current hunk.
      for line in old[i2:i2 + context]:
        yield _diff_line(b" ", line)


def _diff_line(prefix: bytes, line: bytes) -> bytes:
  """
  Return `line` with `prefix`, marking a missing final newline the way
  the `diff` utility does.
  """
  if line.endswith(b"\n"):
    return prefix + line
  return prefix + line + b"\n\\ No newline at end of file\n"


# EOF
