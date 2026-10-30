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

It is an error (exit code 2) if INPUT is not set in the environment or
the named file cannot be read.
"""

import argparse
import os
import re
import subprocess
import sys
import time
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
    args = _parse_command_line(argv)
  except SystemExit as e:
    # argparse exits on error (status 2) and for --help (status 0).
    return e.code if isinstance(e.code, int) else 2

  if args.sleep is not None:
    time.sleep(args.sleep)

  input_name = os.environ.get("INPUT")
  if input_name is None:
    return _error("the INPUT environment variable is not set")
  try:
    with open(input_name, "rb") as f:
      data = f.read()
  except OSError as e:
    return _error(f"cannot read {input_name!r}: {e.strerror}")

  timestamp = _format_timestamp(start_ns)

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

  return 1 if failure is not None else 0


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
      if data.count(opener) != data.count(closer):
        return f"unbalanced {chr(opener)}{chr(closer)} counts"

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
