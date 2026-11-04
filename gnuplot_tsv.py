#!/usr/bin/env python3
"""
Use gnuplot to visualize TSVs created by ./t_accept.py --tsv-log.

Usage:

  $ ./gnuplot_tsv.py [options] <tsvfile> [<tsvfile>...]

Options:

  --show

    Run gnuplot (which must be on the PATH) to pop up a window showing
    the plot, and wait for gnuplot to terminate.

  --output,-o <fname.gp>

    Write the gnuplot script to the specified file.

  --pass-col N

    Treat (1-based) column N as the "pass" column.  If a non-ignored row
    has that column, and its value is different from its most recent
    value (when it was present; or for its first appearance), plot a
    single dot on top of the data line at the corresponding location,
    and label that dot with the new value of "pass".

Behavior:

  Read <tsvfile>s and construct a gnuplot script in memory.

  Each <tsvfile> is expected to have at least these tab-separated
  columns (with no preceding label row):

    * timestamp: unix time of invocation as a decimal number
    * verdict: TRUE or FALSE
    * B: candidate size in bytes

  A well-formed row must have properly-formatted <timestamp> and <B>
  fields.  Ignore rows that have fewer than 3 fields (more than 3 is
  fine), or where those two are improperly formatted.  Also ignore rows
  where the verdict is not "TRUE".

  Each <tsvfile> contributes its own data line, with its Y data labeled
  with the name of its <tsvfile>, omitting path information.

  The X axis of the plot is "reltime", the difference between the
  timestamp for that row and the first timestamp on a non-ignored row
  in its <tsvfile>.

  The plot's X axis is labeled "reltime (s)".

  The Y axis is "B", and is labeled "size (bytes)".

  The title of the plot is "Accepted Size vs. Time".

  After generating the gnuplot script in memory, write to stdout one
  line for each <tsvfile>:

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
from collections.abc import Iterator
from decimal import Decimal
from typing import Optional


# A well-formed timestamp field: a decimal number.
_TIMESTAMP_RE = re.compile(r"[0-9]+(\.[0-9]+)?")

# A well-formed B (size in bytes) field: a nonnegative integer.
_SIZE_RE = re.compile(r"[0-9]+")

# Minimum number of columns a row must have to be well-formed.
_NUM_COLUMNS = 3

# Column indices (0-based) of the fields that are used.
_TIMESTAMP_COL = 0
_VERDICT_COL = 1
_SIZE_COL = 2

# A point where the pass changes: (reltime, B, new pass value).
PassChange = tuple[Decimal, int, str]


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

  tsv_names: list[str] = args.tsvfile

  # For each element of `tsv_names`, its well-formed (reltime, B) pairs
  # and its total number of rows.
  parsed: list[tuple[list[tuple[Decimal, int]], int]] = []

  # With --pass-col, the pass changes for each element of `tsv_names`.
  pass_changes: list[list[PassChange]] = []

  for tsv_name in tsv_names:
    try:
      # 'errors="replace"' means malformed UTF-8 is replaced rather than
      # failing the decode operation, making this script more tolerant.
      with open(tsv_name, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    except OSError as e:
      print(f"gnuplot_tsv.py: error: cannot read {tsv_name!r}: "
            f"{e.strerror}", file=sys.stderr)
      return 2
    parsed.append(parse_tsv(text))
    if args.pass_col is not None:
      pass_changes.append(parse_pass_changes(text, args.pass_col))

  script = make_script(
    [(os.path.basename(tsv_name), points)
     for tsv_name, (points, _) in zip(tsv_names, parsed, strict=True)],
    pass_changes if args.pass_col is not None else None)

  for tsv_name, (points, total_rows) in zip(tsv_names, parsed, strict=True):
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
  Parse `text`, the contents of a TSV file.  Return the (reltime, B)
  pairs of the well-formed rows with a "TRUE" verdict, and the total
  number of rows.
  """
  rows = text.splitlines()
  points = [(reltime, size) for reltime, size, _ in _accepted_rows(rows)]
  return points, len(rows)


def parse_pass_changes(text: str, pass_col: int) -> list[PassChange]:
  """
  Parse `text`, the contents of a TSV file, and return the points among
  the well-formed rows with a "TRUE" verdict where the value in (1-based)
  column `pass_col` differs from its most recent value, or appears for
  the first time.  Rows that lack that column are skipped.

  Rationale for ignoring false verdicts: Although a pass change can (and
  often does) occur on a false verdict, and hence it's tempting to plot
  that, the size is wrong in that case (since it's the size of a
  non-accepted candidate).  The current approach delays the pass marker
  to keep it on the line.
  """
  changes: list[PassChange] = []

  # Most recent value of the pass column, if any.
  prev: Optional[str] = None

  for reltime, size, fields in _accepted_rows(text.splitlines()):
    if len(fields) < pass_col:
      continue
    value = fields[pass_col - 1]
    if value != prev:
      changes.append((reltime, size, value))
      prev = value

  return changes


def _accepted_rows(
  rows: list[str],
) -> Iterator[tuple[Decimal, int, list[str]]]:
  """
  Yield (reltime, B, fields) for each row in `rows` that is well-formed
  and has a "TRUE" verdict, where `fields` are all of its fields.
  """

  # Timestamp of the first well-formed, accepted row.
  first: Decimal | None = None

  for row in rows:
    fields = row.split("\t")
    if len(fields) < _NUM_COLUMNS:
      continue
    timestamp = fields[_TIMESTAMP_COL]
    size = fields[_SIZE_COL]
    if not (_TIMESTAMP_RE.fullmatch(timestamp) and
            _SIZE_RE.fullmatch(size) and
            fields[_VERDICT_COL] == "TRUE"):
      continue

    # Using `Decimal` keeps the difference exact, so the script shows
    # the same digits as the TSV.
    t = Decimal(timestamp)
    if first is None:
      first = t
    yield t - first, int(size), fields


def make_script(
  datasets: list[tuple[str, list[tuple[Decimal, int]]]],
  pass_changes: Optional[list[list[PassChange]]] = None,
) -> str:
  """
  Return a gnuplot script that plots each of `datasets`, a (label,
  points) pair where `points` are (reltime, B) pairs, as its own line
  labeled with `label` in the legend.  The data is embedded in the
  script, and the script waits for the plot window to be closed before
  exiting.

  If `pass_changes` is not None, it has one element per dataset, and
  each of its points is drawn as a dot, labeled with the pass value, in
  the color of that dataset's line.

  Requires that `datasets` is not empty.
  """
  assert datasets
  if pass_changes is not None:
    assert len(pass_changes) == len(datasets)

  # Indices (1-based) of the datasets that have pass changes to draw.
  pass_indices = [
    i for i, changes in enumerate(pass_changes or [], start=1) if changes]

  lines = [
    "set title 'Accepted Size vs. Time'",
    "set xlabel 'reltime (s)'",
    "set ylabel 'size (bytes)'",
  ]

  if pass_indices:
    # Separate data columns only by tabs so a pass value containing
    # spaces or quotes is still a single label.
    lines.append('set datafile separator "\\t"')

  # One data block per dataset, named "$data1", "$data2", etc.
  for i, (_, points) in enumerate(datasets, start=1):
    lines.append(f"$data{i} << EOD")
    lines.extend(f"{reltime}\t{size}" for reltime, size in points)
    lines.append("EOD")

  # One block of pass changes per dataset that has any, named "$pass1",
  # etc., with the same number as the dataset.
  for i in pass_indices:
    assert pass_changes is not None
    lines.append(f"$pass{i} << EOD")
    lines.extend(f"{reltime}\t{size}\t{value}"
                 for reltime, size, value in pass_changes[i-1])
    lines.append("EOD")

  # Use a larger default size and font since I'm using a 4k monitor.
  lines.append('set terminal wxt size 1600,800 font "Arial,20"')

  # Increase the line thickness.
  for i in range(len(datasets)):
    lines.append(f"set linetype {i+1} lw 2")

  # The accepted size only changes at each accepted candidate, so each
  # is drawn as a step function.  The labels are not "enhanced" so that,
  # e.g., "_" in a file name is not treated as a subscript marker.
  # (gnuplot skips a data block with no points, with a warning.)
  plot_elements = [
    f"$data{i} using 1:2 with steps title {_quote(label)} noenhanced"
    for i, (label, _) in enumerate(datasets, start=1)]

  # Each pass change is a dot in its dataset's line color, labeled with
  # the new pass value above and to the right.  These come after all of
  # the data lines so they do not affect the default line colors.
  plot_elements += [
    f"$pass{i} using 1:2:3 with labels point pt 7 lt {i} "
    f"offset char 1,1 notitle noenhanced"
    for i in pass_indices]

  lines.append("plot " + ", \\\n     ".join(plot_elements))

  # Tell gnuplot to wait for the user to close the plot window.
  lines.append("pause mouse close")

  return "".join(line + "\n" for line in lines)


def _quote(s: str) -> str:
  """Return `s` as a gnuplot single-quoted string literal."""
  # In a single-quoted gnuplot string, the only special character is
  # the quote itself, which is written twice.
  return "'" + s.replace("'", "''") + "'"


def _column_number(s: str) -> int:
  """Parse `s` as a 1-based column number, for argparse."""
  try:
    n = int(s)
  except ValueError:
    n = 0
  if n < 1:
    raise argparse.ArgumentTypeError(
      f"invalid column number: {s!r} (must be a positive integer)")
  return n


def _parse_command_line(argv: list[str]) -> argparse.Namespace:
  """Parse `argv`, exiting via SystemExit on error or --help."""
  parser = argparse.ArgumentParser(
    prog="gnuplot_tsv.py",
    description="Use gnuplot to plot candidate size versus time from a "
                "TSV files created by t_accept.py --tsv-log.")
  parser.add_argument(
    "--show", action="store_true",
    help="Run gnuplot to show the plot, and wait for it to exit.")
  parser.add_argument(
    "--output", "-o", metavar="FNAME.gp",
    help="Write the gnuplot script to FNAME.gp.")
  parser.add_argument(
    "--pass-col", metavar="N", type=_column_number,
    help="Mark where the value in (1-based) column N changes.")
  parser.add_argument(
    "tsvfile", nargs="+",
    help="TSV file to read.  Each is plotted as its own line.")
  return parser.parse_args(argv)


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))


# EOF
