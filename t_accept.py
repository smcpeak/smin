#!/usr/bin/env python3
"""
Generic test acceptance program, meant for use while testing smin.

This program reads the file named by the "INPUT" envvar, and performs
some acceptance checks on it, exiting 0 if all pass and 1 if any does
not.

Usage:

  $ INPUT=<input> t_accept.py [options]

Options:

  --has-string <str>

    Require that some input line contains <str> as a substring.

  --has-regex <regex>

    Require that some input line matches <regex>.

  --balanced-delim-counts

    Require that the number of each of open-{paren,bracket,brace}
    characters equals the corresponding number of corresponding closers.
    (This crudely approximates requiring that they be grammatically
    balanced.)

  --before-after <before> <after>

    Require that some line contain <before> as a substring, and that
    some strictly later line contain <after> as a substring.

  --clang

    Require that "clang -fsyntax-only -xc++ $INPUT" exit with code 0.

  --sleep <s>

    Sleep for <s> (a decimal number) seconds at the start, simulating a
    check that takes some time to complete.

  --capture <dir>

    Write the contents of the input file to <dir>/input-<timestamp>
    where <timestamp> is the Unix time of the invocation time as a
    decimal number with 9 decimal digits (i.e., nanosecond precision).

  --log <logfile>

    Append to <logfile> a single line recording the name of the input
    file, the <timestamp> (as described for --capture), the verdict
    (accept or reject), and if --capture, the name of the captured input
    file.

  --input-log <ilogfile>

    After checking acceptance, append to <ilogfile>:

    * A newline.
    * A 72-character separator/header line with either " ACCEPT " or
      " reject " centered between lines of dashes.
    * A line: "Progress: $SMIN_PROGRESS".
    * A unified diff of $INPUT_BEST versus $INPUT showing the change
      under consideration.
    * If the verdict is acceptance, a separator line with " NEW BEST "
      centered between lines of equals-signs, then the contents of
      the input file.

It is an error (exit code 2) if INPUT is not set in the environment or
the named file cannot be read.
"""

import argparse
import difflib
import os
import re
import subprocess
import sys
import time
from collections.abc import Iterator
from typing import Optional


# This function is called from t_accept_test.py (as well as below).
def main(argv: list[str]) -> int:
  """
  Parse the command line `argv` (which excludes the program name),
  perform the functions described in the module usage string, and return
  the appropriate exit code.
  """

  # Nanoseconds since the Unix epoch at invocation.
  start_ns: int = time.time_ns()

  try:
    args: argparse.Namespace = _parse_command_line(argv)
  except SystemExit as e:
    # argparse exits on error (status 2) and for --help (status 0).
    return e.code if isinstance(e.code, int) else 2

  if args.sleep is not None:
    time.sleep(args.sleep)

  input_name: Optional[str] = os.environ.get("INPUT")
  if input_name is None:
    return _error("the INPUT environment variable is not set")
  try:
    with open(input_name, "rb") as f:
      data = f.read()
  except OSError as e:
    return _error(f"cannot read {input_name!r}: {e.strerror}")

  timestamp: str = _format_timestamp(start_ns)

  captured: Optional[str] = None
  if args.capture is not None:
    os.makedirs(args.capture, exist_ok=True)
    captured = os.path.join(args.capture, f"input-{timestamp}")
    with open(captured, "wb") as f:
      f.write(data)

  try:
    failure = _first_failure(args, input_name, data)
  except FileNotFoundError:
    return _error("cannot run clang")

  if failure is not None:
    print(f"reject: {failure}")
  verdict = "reject" if failure is not None else "accept"

  if args.log is not None:
    fields = [input_name, timestamp, verdict]
    if captured is not None:
      fields.append(captured)
    with open(args.log, "a") as f:
      f.write(" ".join(fields) + "\n")

  if args.input_log is not None:
    label = " reject " if failure is not None else " ACCEPT "
    progress = os.environ.get("SMIN_PROGRESS", "None")
    with open(args.input_log, "ab") as f:
      f.write(b"\n" + label.center(72, "-").encode() + b"\n")
      f.write((f"Progress: {progress}\n").encode())
      f.write(_diff_from_best(data))
      if failure is None:
        f.write(" NEW BEST ".center(72, "=").encode() + b"\n")
        f.write(data)

  return 1 if failure is not None else 0


def _diff_from_best(data: bytes) -> bytes:
  """
  Return the diff, for --input-log, from the file named by $INPUT_BEST
  to `data`, or a note saying that file is not available.
  """
  best_name = os.environ.get("INPUT_BEST")
  if best_name is None:
    return b"(INPUT_BEST is not set, so there is no diff.)\n"
  try:
    with open(best_name, "rb") as f:
      best = f.read()
  except OSError:
    return b"(Cannot read INPUT_BEST, so there is no diff.)\n"
  return b"".join(_diff_lines(_split_lines(best), _split_lines(data)))


def _split_lines(data: bytes) -> list[bytes]:
  """
  Split `data` into lines, each including its newline, except that the
  last may lack one.
  """
  return re.findall(rb"[^\n]*\n|[^\n]+$", data)


def _diff_lines(old: list[bytes], new: list[bytes]) -> Iterator[bytes]:
  """
  Yield the lines of a unified diff from `old` to `new`, with three
  lines of context, but without the file header or the line numbers of
  each hunk.  Hunks after the first are preceded by a "@@" line.
  """
  # `SequenceMatcher` is very slow on large inputs with many repeated
  # lines (such as blank lines), but the change being logged is usually
  # small and localized.  So, only compare the lines between the common
  # prefix and suffix, then form the hunks here, taking context lines
  # from anywhere in `old`.
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


def _parse_command_line(argv: list[str]) -> argparse.Namespace:
  """Parse `argv`, exiting via SystemExit on error or --help."""
  parser = argparse.ArgumentParser(
    prog="t_accept.py",
    usage="INPUT=<input> %(prog)s [options]",
    description="Accept (exit 0) or reject (exit 1) the file named by "
                "the INPUT envvar.  The checks may be given more than "
                "once, and all must pass.")
  parser.add_argument(
    "--has-string", action="append", default=[], metavar="STR",
    help="Require that some input line contains STR.")
  parser.add_argument(
    "--has-regex", action="append", default=[], metavar="REGEX",
    help="Require that some input line matches (searching) REGEX.")
  parser.add_argument(
    "--balanced-delim-counts", action="store_true",
    help="Require equal counts of each kind of opener and closer.")
  parser.add_argument(
    "--before-after", action="append", default=[], nargs=2,
    metavar=("BEFORE", "AFTER"),
    help="Require a line containing BEFORE, and a strictly later line "
         "containing AFTER.")
  parser.add_argument(
    "--clang", action="store_true",
    help='Require that "clang -fsyntax-only -xc++ $INPUT" succeeds.')
  parser.add_argument(
    "--sleep", type=float, metavar="S",
    help="Sleep for S seconds at the start.")
  parser.add_argument(
    "--capture", metavar="DIR",
    help="Copy the input to DIR/input-<timestamp>.")
  parser.add_argument(
    "--log", metavar="LOGFILE",
    help="Append a line describing this invocation to LOGFILE.")
  parser.add_argument(
    "--input-log", metavar="ILOGFILE",
    help="Append a verdict header line, minimizer progress status, a "
         "diff describing the change in the candidate, and upon "
         "acceptance, the new best input; all to ILOGFILE.")
  return parser.parse_args(argv)


def _error(message: str) -> int:
  """Print an error `message` and return the exit code for errors."""
  print(f"t_accept.py: error: {message}", file=sys.stderr)
  return 2


def _format_timestamp(ns: int) -> str:
  """Format `ns` nanoseconds as seconds with 9 decimal digits."""
  secs, frac = divmod(ns, 10**9)
  return f"{secs}.{frac:09d}"


def _first_failure(
  args: argparse.Namespace,
  input_name: str,
  data: bytes,
) -> Optional[str]:
  """
  Perform the checks requested by `args` on `data`, the contents of
  `input_name`.  Return a description of the first one that fails, or
  None if all pass.

  The checks are done on bytes, with the command line strings encoded
  the same way the OS encodes file names.  The clang check is done last
  since it is the slowest.
  """
  lines = data.splitlines()

  for s in args.has_string:
    if not any(os.fsencode(s) in line for line in lines):
      return f"no line contains {s!r}"

  for r in args.has_regex:
    regex = re.compile(os.fsencode(r))
    if not any(regex.search(line) for line in lines):
      return f"no line matches {r!r}"

  if args.balanced_delim_counts:
    for opener, closer in (b"()", b"[]", b"{}"):
      n_opener = data.count(opener)
      n_closer = data.count(closer)
      if n_opener != n_closer:
        return (f"unbalanced \"{chr(opener)}{chr(closer)}\" counts" +
                f" ({n_opener} vs. {n_closer})")

  for before, after in args.before_after:
    if not _has_before_after(lines, os.fsencode(before),
                             os.fsencode(after)):
      return f"no line contains {before!r} followed by one with {after!r}"

  if args.clang:
    proc = subprocess.run(
      ["clang", "-fsyntax-only", "-xc++", input_name], check=False)
    if proc.returncode != 0:
      return f"clang exited with code {proc.returncode}"

  return None


def _has_before_after(lines: list[bytes], before: bytes,
                      after: bytes) -> bool:
  """
  True if some element of `lines` contains `before` and a later one
  contains `after`.
  """
  for i, line in enumerate(lines):
    if before in line:
      # Only the first line containing `before` needs to be considered,
      # since it has the most lines after it.
      return any(after in later for later in lines[i+1:])
  return False


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))


# EOF
