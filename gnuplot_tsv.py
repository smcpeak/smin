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

    Treat (1-based) column N as the "pass" column.  If a row has that
    column, and its value is different from its most recent value (when
    it was present; or for its first appearance), plot a single dot on
    top of the data line at the corresponding location, and label that
    dot with the new value of "pass".

    If the verdict is not "TRUE" when the pass changes (which is
    typical), then the Y coordinate of the "corresponding location" is
    the size (B) column from the most recent line that had a "TRUE"
    verdict, as that represents the size of the *accepted* candidate at
    that point.

Behavior:

  Read <tsvfile>s and construct a gnuplot script in memory.

  Each <tsvfile> is expected to have at least these tab-separated
  columns (with no preceding label row):

    * timestamp: unix time of invocation as a decimal number
    * verdict: TRUE or FALSE
    * B: last accepted candidate size in bytes

  A well-formed row must have properly-formatted <timestamp> and <B>
  fields.  Ignore rows that have fewer than 3 fields (more than 3 is
  fine), or where those two are improperly formatted.

  Do not plot rows where the verdict is not "TRUE".  But a row with a
  "FALSE" verdict can still be used to mark a pass change.

  Each <tsvfile> contributes its own data line, with its Y data labeled
  with `label(<tsvfile>)`, computed as follows:

    * Split each <tsvfile> name into a list of elements separated by
      slashes or backslashes (treating them equivalently).
    * While every list has the same first element and at least two
      elements, remove the first element from all of them.
    * While every list has the same last element and at least two
      elements, remove the last element from all of them.
    * Let `label(<tsvfile>)` be the remaining elements, joined by
      forward slashes.

  Note: If there is only one <tsvfile>, then `label(<tsvfile>)` will be
  its final path component.

  The X axis of the plot is "reltime", the difference between the
  timestamp for that row and the first timestamp on a non-ignored row
  in its <tsvfile>.

  The plot's X axis is labeled "reltime (s)".

  The Y axis is "B", and is labeled "size (bytes)".

  The title of the plot is "Accepted Size vs. Time".

  After generating the gnuplot script in memory, write to stdout one
  line for each <tsvfile>:

    <tsvfile> has <t> rows (a=<a>, m=<m>).

  where <tsvfile> does include its path info, <a> is the number of
  rows where the verdict is "TRUE", and <m> is the number of rows that
  were malformed (too few columns, or malformed timestamp or size).

  If --show, print:

    Per --show, running gnuplot and waiting for it ...

  If neither --show or --output is passed, also print:

    Run with --show to see it, or --output to save the gnuplot script.

"""

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
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


@dataclass
class DataSeries:
  """
  Data for one TSV file.
  """

  # Name of the file, as given on the command line (including any path
  # information).
  tsv_name: str

  # Total number of rows in the file.
  num_rows: int = 0

  # Number of rows that are malformed: too few columns, or a malformed
  # timestamp or size.  These rows are otherwise ignored.
  num_malformed_rows: int = 0

  # Points to plot as a stepped line, as (reltime, B) pairs, showing
  # where the input file was successfully reduced in size.
  #
  # The number of points is typically less than `num_rows` because it
  # only includes data for rows whose verdict was "TRUE".
  points: list[tuple[Decimal, int]] = field(default_factory=list)

  # A point corresponding to a change in the --pass-col value.  We plot
  # a labeled point on each one.  This is empty if --pass-col was not
  # passed.
  pass_changes: list[PassChange] = field(default_factory=list)


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

  # The data for each TSV file, in command line order.
  series: list[DataSeries] = []

  for tsv_name in args.tsvfile:
    try:
      series.append(parse_tsv(tsv_name, args.pass_col))
    except OSError as e:
      print(f"gnuplot_tsv.py: error: cannot read {tsv_name!r}: "
            f"{e.strerror}", file=sys.stderr)
      return 2

  script = make_script(series)

  for ds in series:
    print(f"{ds.tsv_name} has {ds.num_rows} rows "
          f"(a={len(ds.points)}, m={ds.num_malformed_rows}).")

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


def parse_tsv(tsv_name: str, pass_col: Optional[int] = None) -> DataSeries:
  """
  Read and parse the TSV file `tsv_name`, and return its data, as
  described for `parse_tsv_text`.  Raise OSError if it cannot be read.
  """
  # 'errors="replace"' means malformed UTF-8 is replaced rather than
  # failing the decode operation, making this script more tolerant.
  with open(tsv_name, "r", encoding="utf-8", errors="replace") as f:
    text = f.read()

  return parse_tsv_text(tsv_name, text, pass_col)


def parse_tsv_text(
  tsv_name: str,
  text: str,
  pass_col: Optional[int] = None,
) -> DataSeries:
  """
  Parse `text`, the contents of the TSV file `tsv_name`, and return its
  data.

  The points are the (reltime, B) pairs of the well-formed rows with a
  "TRUE" verdict.  reltime is measured from the first well-formed row,
  whatever its verdict.

  If `pass_col` is not None, the pass changes are the well-formed rows,
  with any verdict, where the value in (1-based) column `pass_col`
  differs from its most recent value, or appears for the first time.
  Rows that lack that column are skipped for this purpose.  Each change
  is placed at its row's reltime, but with the most recently accepted
  size, so it is on the plotted line.  A change before the first
  accepted row has no such size, so it is instead marked at that row.
  """
  ds = DataSeries(tsv_name)

  # Timestamp of the first well-formed row.
  first: Optional[Decimal] = None

  # Size from the most recent well-formed row with a "TRUE" verdict.
  accepted_size: Optional[int] = None

  # Most recent value of the pass column that has been marked, if any.
  prev_pass: Optional[str] = None

  for row in text.splitlines():
    ds.num_rows += 1

    # Require sufficient columns, and well-formed time and size.
    fields = row.split("\t")
    timestamp = fields[_TIMESTAMP_COL] if len(fields) >= _NUM_COLUMNS else ""
    size = fields[_SIZE_COL] if len(fields) >= _NUM_COLUMNS else ""
    if not (_TIMESTAMP_RE.fullmatch(timestamp) and
            _SIZE_RE.fullmatch(size)):
      ds.num_malformed_rows += 1
      continue

    # Compute "reltime" by subtracting the first time we saw.  (Using
    # `Decimal` keeps the difference exact, so the script shows the same
    # digits as the TSV.)
    t = Decimal(timestamp)
    if first is None:
      first = t
    reltime = t - first

    # Only accepted candidates are plotted, since otherwise the size is
    # of a non-accepted candidate, which does not tell us much.
    if fields[_VERDICT_COL] == "TRUE":
      accepted_size = int(size)
      ds.points.append((reltime, accepted_size))

    # If requested, determine where the pass changes occur.  Typically
    # that is on a rejected row, but the dot goes on the line, at the
    # accepted size.
    if (pass_col is not None and
        len(fields) >= pass_col and
        accepted_size is not None):
      value = fields[pass_col - 1]
      if value != prev_pass:
        ds.pass_changes.append((reltime, accepted_size, value))
        prev_pass = value

  return ds


def compute_labels(fnames: list[str]) -> list[str]:
  """
  Return the legend label for each of `fnames`, in the same order, as
  `label(<tsvfile>)` is described in the module docstring: the name
  elements remaining after removing those at the front and back that
  are the same for all names.
  """
  # Each name as a list of elements, separated by either kind of slash.
  elts: list[list[str]] = [re.split(r"[/\\]", f) for f in fnames]

  # Remove common leading elements.
  while (elts and
         all(len(e) >= 2 for e in elts) and
         all(e[0] == elts[0][0] for e in elts)):
    elts = [e[1:] for e in elts]

  # Remove common trailing elements.
  while (elts and
         all(len(e) >= 2 for e in elts) and
         all(e[-1] == elts[0][-1] for e in elts)):
    elts = [e[:-1] for e in elts]

  return ["/".join(e) for e in elts]


def make_script(datasets: list[DataSeries]) -> str:
  """
  Return a gnuplot script that plots each of `datasets` as its own line,
  labeled in the legend as computed by `compute_labels`.
  Each of its pass changes is drawn as a dot, labeled with the
  pass value, in the color of that line.  The data is embedded in the
  script, and the script waits for the plot window to be closed before
  exiting.

  Requires that `datasets` is not empty.
  """
  assert datasets

  # Indices (1-based) of the datasets that have pass changes to draw.
  pass_indices = [
    i for i, ds in enumerate(datasets, start=1) if ds.pass_changes]

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
  for i, ds in enumerate(datasets, start=1):
    lines.append(f"$data{i} << EOD")
    lines.extend(f"{reltime}\t{size}" for reltime, size in ds.points)
    lines.append("EOD")

  # One block of pass changes per dataset that has any, named "$pass1",
  # etc., with the same number as the dataset.
  for i in pass_indices:
    lines.append(f"$pass{i} << EOD")
    lines.extend(f"{reltime}\t{size}\t{value}"
                 for reltime, size, value in datasets[i-1].pass_changes)
    lines.append("EOD")

  # Use a larger default size and font since I'm using a 4k monitor.
  #
  # The syntax for setting size and font also forces me to specify a
  # terminal type.  Originally I had "wxt" (which uses wxWidgets) but
  # that implementation seems extremely buggy when doing things like
  # zooming.  The "qt" implementation works much better.
  lines.append('set terminal qt size 1600,800 font "Arial,20"')

  # Increase the line thickness.
  for i in range(len(datasets)):
    lines.append(f"set linetype {i+1} lw 2")

  # The accepted size only changes at each accepted candidate, so each
  # is drawn as a step function.  The labels are not "enhanced" so that,
  # e.g., "_" in a file name is not treated as a subscript marker.
  # (gnuplot skips a data block with no points, with a warning.)
  labels = compute_labels([ds.tsv_name for ds in datasets])
  plot_elements = [
    f"$data{i} using 1:2 with steps "
    f"title {_quote(label)} noenhanced"
    for i, label in enumerate(labels, start=1)]

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
