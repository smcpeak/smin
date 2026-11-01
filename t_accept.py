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

  --reject

    Reject all inputs except for the first, which is recognized by the
    fact that the $INPUT_BEST file does not exist.

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
      under consideration.  Long runs of deletions are summarized.

  --log-new-best

    With --input-log, if the verdict is acceptance, add a separator line
    with " NEW BEST " centered between lines of equals-signs, then the
    contents of the input file.

It is an error (exit code 2) if INPUT is not set in the environment or
the named file cannot be read.
"""

# It is somewhat redundant to have the options documented in both the
# module docstring and the --help text produced by argparse.  I do this
# because my current workflow is that I modify the docstring, then ask
# Claude to implement my change.  So the docstring acts as the
# specification, and the --help output is part of the implementation.

import argparse
import os
import re
import subprocess
import sys
import time
from typing import Optional

from byte_range import ByteRange
from diff_lines import diff_lines


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
      if failure is None and args.log_new_best:
        f.write(" NEW BEST ".center(72, "=").encode() + b"\n")
        f.write(data)

  return 1 if failure is not None else 0


def _diff_from_best(data: bytes) -> bytes:
  """
  Return the diff, for --input-log, from the file named by $INPUT_BEST
  to `data`, or a note saying that file is not available.

  If the envvar CHANGED_BYTE_RANGE is set to "A-B", then [A,B) is passed
  to `diff_lines` as its `changed_byte_range` parameter.  If it is not
  set or its value does not conform, it is ignored.
  """
  best_name = os.environ.get("INPUT_BEST")
  if best_name is None:
    return b"(INPUT_BEST is not set, so there is no diff.)\n"
  try:
    with open(best_name, "rb") as f:
      best = f.read()
  except OSError:
    return b"(Cannot read INPUT_BEST, so there is no diff.)\n"
  return b"".join(diff_lines(_split_lines(best), _split_lines(data),
                             _changed_byte_range()))


def _changed_byte_range() -> Optional[ByteRange]:
  """
  Return the range in the CHANGED_BYTE_RANGE envvar, or None if it is
  not set or not of the form "A-B" with A <= B.
  """
  m = re.fullmatch(r"(\d+)-(\d+)",
                   os.environ.get("CHANGED_BYTE_RANGE", ""), re.ASCII)
  if m is None:
    return None
  start, stop = int(m.group(1)), int(m.group(2))
  if start > stop:
    return None
  return ByteRange(start, stop)


def _split_lines(data: bytes) -> list[bytes]:
  """
  Split `data` into lines, each including its newline, except that the
  last may lack one.
  """
  return re.findall(rb"[^\n]*\n|[^\n]+$", data)


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
    "--reject", action="store_true",
    help="Reject every input except the first, which is recognized by "
         "the INPUT_BEST file not existing.")
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
    help="Append a verdict header line, minimizer progress status, and "
         "a diff describing the change in the candidate to ILOGFILE.")
  parser.add_argument(
    "--log-new-best", action="store_true",
    help="With --input-log, upon acceptance, also append the new best "
         "input.")
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

  if args.reject:
    # If INPUT_BEST is not set, there is no such file, so the input is
    # treated as the first.
    best_name = os.environ.get("INPUT_BEST")
    if best_name is not None and os.path.exists(best_name):
      return "--reject, and INPUT_BEST exists"

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
