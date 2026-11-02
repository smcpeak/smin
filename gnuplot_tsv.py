#!/usr/bin/env python3
"""
Use gnuplot to visualize a TSV created by ./t_accept.py --tsv-log.

Usage:

  $ ./gnuplot_tsv.py [options] <tsvfile>

Options:

  --show

    Run gnuplot (which must be on the PATH) to pop up a window showing
    the plot, and wait for gnuplot to terminate.

  --output,-o <fname.gp>

    Write the gnuplot script to the specified file.

Behavior:

  Read <tsvfile> and construct a gnuplot script in memory.

  The <tsvfile> is expected to have these tab-separated columns (with no
  preceding label row):

    * timestamp: unix time of invocation as a decimal number
    * verdict: TRUE or FALSE
    * N: invocation number
    * S: candidate size in tokens
    * P: pass number
    * Pm: maximum pass number
    * F: completion fraction as an integer in [0,99]
    * R: number of tokens removed when making the candidate

  A well-formed row must have properly-formatted <timestamp> and <S>
  fields.  Ignore rows that do not have enough fields, or where those
  two are improperly formatted.  Don't validate the other columns.

  The X axis of the plot is "reltime", the difference between the
  timestamp for that row and the first timestamp on a non-ignored row.
  The plot's X axis is labeled "reltime (s)".

  The Y axis is "S", and is labeled "size (tokens)".

  The title of the plot is <tsvfile>, but with path information removed.

  After generating the gnuplot script in memory, write to stdout:

    <tsvfile> has <n> rows of well-formed data out of <t> rows in total.

  (where <tsvfile> does include its path info).

  If --show, print:

    Per --show, running gnuplot and waiting for it ...

  If neither --show or --output is passed, also print:

    Run with --show to see it, or --output to save the gnuplot script.

"""

import argparse
import os
import re
import subprocess
import sys
from decimal import Decimal


# A well-formed timestamp field: a decimal number.
_TIMESTAMP_RE = re.compile(r"[0-9]+(\.[0-9]+)?")

# A well-formed S (size) field: a nonnegative integer.
_SIZE_RE = re.compile(r"[0-9]+")

# Number of columns a row must have to be well-formed.
_NUM_COLUMNS = 8

# Column indices (0-based) of the fields that are used.
_TIMESTAMP_COL = 0
_SIZE_COL = 3


def main(argv: list[str]) -> int:
  """
  Parse the command line `argv` (which excludes the program name),
  perform the functions described in the module docstring.

  Return the exit code: 0 for success, 2 for error.
  """
  try:
    args = _parse_command_line(argv)
  except SystemExit as e:
    # argparse exits on error (status 2) and for --help (status 0).
    return e.code if isinstance(e.code, int) else 2

  tsv_name: str = args.tsvfile
  try:
    # 'errors="replace"' means malformed UTF-8 is replaced rather than
    # failing the decode operation, making this script more tolerant.
    with open(tsv_name, "r", encoding="utf-8", errors="replace") as f:
      text = f.read()
  except OSError as e:
    print(f"gnuplot_tsv.py: error: cannot read {tsv_name!r}: {e.strerror}",
          file=sys.stderr)
    return 2

  points, total_rows = parse_tsv(text)
  script = make_script(os.path.basename(tsv_name), points)

  print(f"{tsv_name} has {len(points)} rows of well-formed data out of "
        f"{total_rows} rows in total.")

  if args.output is not None:
    with open(args.output, "w", encoding="utf-8") as f:
      f.write(script)

  if args.show:
    try:
      print("Per --show, running gnuplot and waiting for it ...")
      proc = subprocess.run(["gnuplot", "-"], input=script, text=True,
                            check=False)
    except FileNotFoundError:
      print("gnuplot_tsv.py: error: cannot run gnuplot", file=sys.stderr)
      return 2
    if proc.returncode != 0:
      print(f"gnuplot_tsv.py: gnuplot exited with code {proc.returncode}",
            file=sys.stderr)
      return 2

  if not args.show and args.output is None:
    print("Run with --show to see it, or --output to save the gnuplot "
          "script.")

  return 0


def parse_tsv(text: str) -> tuple[list[tuple[Decimal, int]], int]:
  """
  Parse `text`, the contents of a TSV file.  Return the (reltime, S)
  pairs of the well-formed rows, and the total number of rows.
  """
  rows = text.splitlines()

  # Timestamp of the first well-formed row.
  first: Decimal | None = None

  points: list[tuple[Decimal, int]] = []
  for row in rows:
    fields = row.split("\t")
    if len(fields) < _NUM_COLUMNS:
      continue
    timestamp = fields[_TIMESTAMP_COL]
    size = fields[_SIZE_COL]
    if not (_TIMESTAMP_RE.fullmatch(timestamp) and
            _SIZE_RE.fullmatch(size)):
      continue

    # Using `Decimal` keeps the difference exact, so the script shows
    # the same digits as the TSV.
    t = Decimal(timestamp)
    if first is None:
      first = t
    points.append((t - first, int(size)))

  return points, len(rows)


def make_script(title: str, points: list[tuple[Decimal, int]]) -> str:
  """
  Return a gnuplot script that plots `points`, (reltime, S) pairs, with
  `title`.  The data is embedded in the script, and the script waits for
  the plot window to be closed before exiting.
  """
  lines = [
    # The title is not "enhanced" so that, e.g., "_" in a file name is
    # not treated as a subscript marker.
    f"set title {_quote(title)} noenhanced",
    "set xlabel 'reltime (s)'",
    "set ylabel 'size (tokens)'",
    "set key off",
    "$data << EOD",
    *(f"{reltime}\t{size}" for reltime, size in points),
    "EOD",
    # S only changes when a candidate is accepted, so it is drawn as
    # a step function.
    "plot $data using 1:2 with steps",

    # Tell gnuplot to wait for the user to close the plot window.
    "pause mouse close",
  ]
  return "".join(line + "\n" for line in lines)


def _quote(s: str) -> str:
  """Return `s` as a gnuplot single-quoted string literal."""
  # In a single-quoted gnuplot string, the only special character is
  # the quote itself, which is written twice.
  return "'" + s.replace("'", "''") + "'"


def _parse_command_line(argv: list[str]) -> argparse.Namespace:
  """Parse `argv`, exiting via SystemExit on error or --help."""
  parser = argparse.ArgumentParser(
    prog="gnuplot_tsv.py",
    description="Use gnuplot to plot candidate size versus time from a "
                "TSV file created by t_accept.py --tsv-log.")
  parser.add_argument(
    "--show", action="store_true",
    help="Run gnuplot to show the plot, and wait for it to exit.")
  parser.add_argument(
    "--output", "-o", metavar="FNAME.gp",
    help="Write the gnuplot script to FNAME.gp.")
  parser.add_argument(
    "tsvfile",
    help="TSV file to read.")
  return parser.parse_args(argv)


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))


# EOF
