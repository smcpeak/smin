# gnuplot_tsv_test.py
"""
Unit tests for gnuplot_tsv.
"""

from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

from gnuplot_tsv import (
  DataSeries,
  PassChange,
  main,
  make_script,
  parse_tsv,
  parse_tsv_text,
)
from test_util import dedent


# The fake gnuplot is a shell script.
POSIX = os.name == "posix"


def row(timestamp: str, size: str, verdict: str = "TRUE") -> str:
  """
  A TSV row with `timestamp`, `verdict`, and `size` (in bytes), followed
  by plausible progress fields.
  """
  return "\t".join([timestamp, verdict, size,
                    "1", "20", "1", "2", "0", "3"]) + "\n"


# The (1-based) column of P, the pass number, in rows made by `prow`, as
# written by t_accept.py --tsv-log.
PASS_COL = 6


def prow(timestamp: str, size: str, pass_num: str,
         verdict: str = "TRUE") -> str:
  """Like `row`, but with `pass_num` in column `PASS_COL`."""
  return "\t".join([timestamp, verdict, size,
                    "1", "20", pass_num, "9", "0", "3"]) + "\n"


class ParseTestCase(unittest.TestCase):
  """Base class for tests of `parse_tsv_text`."""

  # File name passed to `parse_tsv_text`.
  name = "dir/log.tsv"

  def parse(self, text: str, pass_col: int | None = None) -> DataSeries:
    """Parse `text` as the contents of `name`, with `pass_col`."""
    return parse_tsv_text(self.name, text, pass_col)


class ParseTsvTest(ParseTestCase):
  def test_empty(self) -> None:
    self.assertEqual(self.parse(""), DataSeries(self.name))

  def test_well_formed(self) -> None:
    text = (row("100.5", "10") +
            row("100.75", "6") +
            row("101.000000001", "6"))
    self.assertEqual(self.parse(text), DataSeries(self.name, num_rows=3,
                                                  points=[
      (Decimal(0), 10),
      (Decimal("0.25"), 6),
      # The difference is exact.
      (Decimal("0.500000001"), 6),
    ]))

  def test_rejected_rows_not_plotted(self) -> None:
    # Only a verdict of exactly "TRUE" is plotted.  But the reltime is
    # measured from the first well-formed row, whatever its verdict, and
    # rows with other verdicts are not malformed.
    text = (row("99.0", "12", "FALSE") +
            row("100.0", "10") +
            row("100.5", "8", "FALSE") +
            row("101.0", "9", "true") +
            row("101.5", "9", "maybe") +
            row("102.0", "7"))
    self.assertEqual(self.parse(text), DataSeries(
      self.name, num_rows=6,
      points=[(Decimal(1), 10), (Decimal(3), 7)]))

  def test_integer_timestamp(self) -> None:
    self.assertEqual(self.parse(row("7", "1") + row("9", "0")), DataSeries(
      self.name, num_rows=2, points=[(Decimal(0), 1), (Decimal(2), 0)]))

  def test_malformed_rows(self) -> None:
    text = (
      # Too few fields.
      "100.0\tTRUE\n" +
      row("x100.0", "10") +
      row("100.0", "ten") +
      row("1e2", "10") +
      row("100.", "10") +
      row("100.0", "") +
      row("", "10") +
      "\n" +
      row("101.5", "8") +
      row("102.5", "7"))

    # Malformed rows are counted, but otherwise ignored, so the reltime
    # is measured from the first well-formed row.
    self.assertEqual(self.parse(text), DataSeries(
      self.name, num_rows=10, num_malformed_rows=8,
      points=[(Decimal(0), 8), (Decimal(1), 7)]))

  def test_malformed_rejected_row(self) -> None:
    # A malformed row is counted as such whatever its verdict.
    text = row("x", "10", "FALSE") + row("1.0", "9")
    self.assertEqual(self.parse(text), DataSeries(
      self.name, num_rows=2, num_malformed_rows=1,
      points=[(Decimal(0), 9)]))

  def test_other_columns_not_validated(self) -> None:
    text = "5.0\tTRUE\t3\tN\tS\tP\tPm\tF\tR\n"
    self.assertEqual(self.parse(text), DataSeries(
      self.name, num_rows=1, points=[(Decimal(0), 3)]))

  def test_three_fields_enough(self) -> None:
    # The initial test's row has no progress fields.
    self.assertEqual(self.parse("5.0\tTRUE\t30\n" + row("6.0", "20")),
                     DataSeries(self.name, num_rows=2,
                                points=[(Decimal(0), 30), (Decimal(1), 20)]))

  def test_extra_fields_allowed(self) -> None:
    self.assertEqual(self.parse(row("5.0", "3").rstrip("\n") + "\textra\n"),
                     DataSeries(self.name, num_rows=1,
                                points=[(Decimal(0), 3)]))

  def test_no_final_newline(self) -> None:
    self.assertEqual(self.parse(row("5.0", "3") + row("6.0", "2").rstrip()),
                     DataSeries(self.name, num_rows=2,
                                points=[(Decimal(0), 3), (Decimal(1), 2)]))


class ParseTsvFileTest(unittest.TestCase):
  """Tests of `parse_tsv`, which reads the file."""

  def setUp(self) -> None:
    self.temp_dir = tempfile.TemporaryDirectory()
    self.path = Path(self.temp_dir.name) / "log.tsv"

  def tearDown(self) -> None:
    self.temp_dir.cleanup()

  def test_read(self) -> None:
    self.path.write_text(prow("5.0", "3", "1") + prow("6.0", "2", "2"))
    self.assertEqual(parse_tsv(str(self.path), PASS_COL), DataSeries(
      str(self.path), num_rows=2,
      points=[(Decimal(0), 3), (Decimal(1), 2)],
      pass_changes=[(Decimal(0), 3, "1"), (Decimal(1), 2, "2")]))

  def test_missing_file(self) -> None:
    with self.assertRaises(OSError):
      parse_tsv(str(self.path))

  def test_invalid_utf8(self) -> None:
    # Malformed UTF-8 is replaced rather than causing an error.  Here,
    # it makes a malformed row.
    self.path.write_bytes(b"\xff\n" + row("5.0", "3").encode())
    self.assertEqual(parse_tsv(str(self.path)), DataSeries(
      str(self.path), num_rows=2, num_malformed_rows=1,
      points=[(Decimal(0), 3)]))


class ParseTsvPassColTest(ParseTestCase):
  def test_empty(self) -> None:
    self.assertEqual(self.parse("", PASS_COL).pass_changes, [])

  def test_changes(self) -> None:
    # The first appearance counts as a change, and repeated values do
    # not.  A value can recur after a different one.
    text = (prow("100.0", "50", "1") +
            prow("100.5", "40", "1") +
            prow("101.0", "30", "2") +
            prow("101.5", "20", "2") +
            prow("102.0", "15", "1"))
    self.assertEqual(self.parse(text, PASS_COL).pass_changes, [
      (Decimal("0.0"), 50, "1"),
      (Decimal("1.0"), 30, "2"),
      (Decimal("2.0"), 15, "1"),
    ])

  def test_rows_without_column(self) -> None:
    # Rows lacking the column, like the initial test's, are skipped, and
    # do not affect what the most recent value was.  They do still set
    # the origin of reltime and the accepted size.
    text = ("100.0\tTRUE\t60\n" +
            prow("101.0", "50", "1") +
            "102.0\tTRUE\t45\n" +
            prow("103.0", "40", "1") +
            "103.5\tTRUE\t35\n" +
            prow("104.0", "30", "2", "FALSE"))
    self.assertEqual(self.parse(text, PASS_COL).pass_changes, [
      (Decimal("1.0"), 50, "1"),
      (Decimal("4.0"), 35, "2"),
    ])

  def test_change_on_rejected_row(self) -> None:
    # The change is marked at the rejected row's reltime, but with the
    # most recently accepted size, which is where the plotted line is.
    text = (prow("100.0", "50", "1") +
            prow("101.0", "45", "1", "FALSE") +
            prow("102.0", "40", "1") +
            prow("103.0", "35", "2", "FALSE") +
            prow("104.0", "38", "2", "FALSE") +
            prow("105.0", "30", "2"))
    self.assertEqual(self.parse(text, PASS_COL), DataSeries(
      self.name, num_rows=6,
      points=[(Decimal("0.0"), 50), (Decimal("2.0"), 40),
              (Decimal("5.0"), 30)],
      pass_changes=[(Decimal("0.0"), 50, "1"), (Decimal("3.0"), 40, "2")]))

  def test_points_unaffected(self) -> None:
    # The points and row counts are the same as without a pass column.
    text = (prow("100.0", "50", "1") +
            prow("101.0", "45", "2", "FALSE") +
            prow("x", "50", "2") +
            prow("102.0", "40", "2"))
    with_col = self.parse(text, PASS_COL)
    without = self.parse(text)
    self.assertEqual(with_col.points, without.points)
    self.assertEqual(with_col.num_rows, without.num_rows)
    self.assertEqual(with_col.num_malformed_rows,
                     without.num_malformed_rows)
    self.assertEqual(without.pass_changes, [])

  def test_malformed_rows_ignored(self) -> None:
    # A malformed row does not mark a change, even if it has the column.
    text = (prow("100.0", "50", "1") +
            prow("x", "50", "2") +
            prow("101.0", "40", "1"))
    self.assertEqual(self.parse(text, PASS_COL).pass_changes,
                     [(Decimal("0.0"), 50, "1")])

  def test_change_before_first_accepted(self) -> None:
    # Before the first accepted row, there is no line to put the dot on,
    # so the change is marked at the first accepted row instead.
    text = (prow("100.0", "50", "1", "FALSE") +
            prow("101.0", "45", "2", "FALSE") +
            prow("102.0", "40", "2") +
            prow("103.0", "35", "3", "FALSE"))
    self.assertEqual(self.parse(text, PASS_COL).pass_changes, [
      (Decimal("2.0"), 40, "2"),
      (Decimal("3.0"), 40, "3"),
    ])

  def test_any_value(self) -> None:
    # The value is not validated, and is compared as a string.
    text = (prow("1", "5", "") +
            prow("2", "4", "a b") +
            prow("3", "3", "01") +
            prow("4", "2", "1"))
    self.assertEqual(self.parse(text, PASS_COL).pass_changes, [
      (Decimal(0), 5, ""),
      (Decimal(1), 4, "a b"),
      (Decimal(2), 3, "01"),
      (Decimal(3), 2, "1"),
    ])

  def test_other_columns(self) -> None:
    # Any column can be used, including the required ones.
    text = prow("1", "5", "1") + prow("2", "4", "1")
    self.assertEqual(self.parse(text, 3).pass_changes,
                     [(Decimal(0), 5, "5"), (Decimal(1), 4, "4")])
    self.assertEqual(self.parse(text, 10).pass_changes, [])


def series(tsv_name: str, points: list[tuple[Decimal, int]],
           pass_changes: list[PassChange] | None = None) -> DataSeries:
  """A `DataSeries` for `tsv_name` with `points` and `pass_changes`."""
  return DataSeries(tsv_name, num_rows=len(points), points=points,
                    pass_changes=pass_changes or [])


class MakeScriptTest(unittest.TestCase):
  def test_one_dataset(self) -> None:
    script = make_script([series("log.tsv", [(Decimal(0), 10),
                                             (Decimal("0.25"), 6)])])
    self.assertEqual(script, dedent("""
      set title 'Accepted Size vs. Time'
      set xlabel 'reltime (s)'
      set ylabel 'size (bytes)'
      $data1 << EOD
      0\t10
      0.25\t6
      EOD
      set terminal wxt size 1600,800 font "Arial,20"
      set linetype 1 lw 2
      plot $data1 using 1:2 with steps title 'log.tsv' noenhanced
      pause mouse close
      """))

  def test_multiple_datasets(self) -> None:
    # Each dataset has its own data block and plot element.  A dataset
    # with no points is still included.
    script = make_script([
      series("a.tsv", [(Decimal(0), 10)]),
      series("b.tsv", []),
      series("c.tsv", [(Decimal(0), 7), (Decimal(3), 5)]),
    ])
    self.assertEqual(script, dedent("""
      set title 'Accepted Size vs. Time'
      set xlabel 'reltime (s)'
      set ylabel 'size (bytes)'
      $data1 << EOD
      0\t10
      EOD
      $data2 << EOD
      EOD
      $data3 << EOD
      0\t7
      3\t5
      EOD
      set terminal wxt size 1600,800 font "Arial,20"
      set linetype 1 lw 2
      set linetype 2 lw 2
      set linetype 3 lw 2
      plot $data1 using 1:2 with steps title 'a.tsv' noenhanced, \\
           $data2 using 1:2 with steps title 'b.tsv' noenhanced, \\
           $data3 using 1:2 with steps title 'c.tsv' noenhanced
      pause mouse close
      """))

  def test_pass_changes(self) -> None:
    # Only datasets with pass changes get a "$passN" block and a plot
    # element, numbered to match the dataset, and placed after all of
    # the data lines.
    script = make_script([
      series("a.tsv", [(Decimal(0), 10), (Decimal(2), 6)],
             [(Decimal(0), 10, "1"), (Decimal(2), 6, "2")]),
      series("b.tsv", [(Decimal(0), 7)]),
      series("c.tsv", [(Decimal(0), 9), (Decimal(1), 8)],
             [(Decimal(1), 8, "x y")]),
    ])
    self.assertEqual(script, dedent("""
      set title 'Accepted Size vs. Time'
      set xlabel 'reltime (s)'
      set ylabel 'size (bytes)'
      set datafile separator "\\t"
      $data1 << EOD
      0\t10
      2\t6
      EOD
      $data2 << EOD
      0\t7
      EOD
      $data3 << EOD
      0\t9
      1\t8
      EOD
      $pass1 << EOD
      0\t10\t1
      2\t6\t2
      EOD
      $pass3 << EOD
      1\t8\tx y
      EOD
      set terminal wxt size 1600,800 font "Arial,20"
      set linetype 1 lw 2
      set linetype 2 lw 2
      set linetype 3 lw 2
      plot $data1 using 1:2 with steps title 'a.tsv' noenhanced, \\
           $data2 using 1:2 with steps title 'b.tsv' noenhanced, \\
           $data3 using 1:2 with steps title 'c.tsv' noenhanced, \\
           $pass1 using 1:2:3 with labels point pt 7 lt 1 offset char 1,1 notitle noenhanced, \\
           $pass3 using 1:2:3 with labels point pt 7 lt 3 offset char 1,1 notitle noenhanced
      pause mouse close
      """))

  def test_label_quoted(self) -> None:
    script = make_script([series("it's.tsv", [])])
    self.assertIn(" title 'it''s.tsv' noenhanced\n", script)

  def test_label_without_path(self) -> None:
    script = make_script([series(os.path.join("dir", "sub", "a.tsv"), [])])
    self.assertIn(" title 'a.tsv' noenhanced\n", script)


class MainTest(unittest.TestCase):
  def setUp(self) -> None:
    self.temp_dir = tempfile.TemporaryDirectory()
    self.dir = Path(self.temp_dir.name)
    self.tsv_path = self.dir / "run_1.tsv"
    self.tsv_path.write_text(
      row("100.0", "10") + "junk\n" + row("101.5", "4"))

    # Output of the most recent `run_main`.
    self.out = ""
    self.err = ""

  def tearDown(self) -> None:
    self.temp_dir.cleanup()

  def run_main(self, argv: list[str],
               env: dict[str, str] | None = None) -> int:
    """
    Run `main(argv)` with additional environment `env`, and return the
    exit code.
    """
    out = io.StringIO()
    err = io.StringIO()
    with mock.patch.dict(os.environ, env or {}), \
         contextlib.redirect_stdout(out), \
         contextlib.redirect_stderr(err):
      code = main(argv)
    self.out = out.getvalue()
    self.err = err.getvalue()
    return code

  def summary_line(self) -> str:
    return f"{self.tsv_path} has 3 rows (a=2, m=1).\n"

  def waiting_line(self) -> str:
    return "Per --show, running gnuplot and waiting for it ...\n"

  # The script for `tsv_path`.  The label has no path information, and
  # the first reltime is "0.0" since it is computed as "100.0 - 100.0".
  EXPECTED_SCRIPT = dedent("""
    set title 'Accepted Size vs. Time'
    set xlabel 'reltime (s)'
    set ylabel 'size (bytes)'
    $data1 << EOD
    0.0\t10
    1.5\t4
    EOD
    set terminal wxt size 1600,800 font "Arial,20"
    set linetype 1 lw 2
    plot $data1 using 1:2 with steps title 'run_1.tsv' noenhanced
    pause mouse close
    """)

  HINT_LINE = ("Run with --show to see it, or --output to save the "
               "gnuplot script.\n")

  def test_no_options(self) -> None:
    self.assertEqual(self.run_main([str(self.tsv_path)]), 0)
    self.assertEqual(self.out, self.summary_line() + self.HINT_LINE)
    self.assertEqual(self.err, "")

  def test_output(self) -> None:
    for option in ["--output", "-o"]:
      gp = self.dir / f"plot{option}.gp"
      self.assertEqual(
        self.run_main([option, str(gp), str(self.tsv_path)]), 0)
      self.assertEqual(self.out, self.summary_line())

      self.assertEqual(gp.read_text(), self.EXPECTED_SCRIPT)

  def test_multiple_files(self) -> None:
    # A second file, in another directory, with different timestamps.
    other_dir = self.dir / "other"
    other_dir.mkdir()
    other = other_dir / "run_2.tsv"
    other.write_text(row("500", "8") + row("503", "5") + row("504", "2"))

    gp = self.dir / "plot.gp"
    self.assertEqual(
      self.run_main(["-o", str(gp), str(self.tsv_path), str(other)]), 0)

    # One summary line per file, in command line order, with paths.
    self.assertEqual(self.out,
      self.summary_line() +
      f"{other} has 3 rows (a=3, m=0).\n")

    # Each file's reltime is measured from its own first timestamp, and
    # its label has no path information.
    self.assertEqual(gp.read_text(), dedent("""
      set title 'Accepted Size vs. Time'
      set xlabel 'reltime (s)'
      set ylabel 'size (bytes)'
      $data1 << EOD
      0.0\t10
      1.5\t4
      EOD
      $data2 << EOD
      0\t8
      3\t5
      4\t2
      EOD
      set terminal wxt size 1600,800 font "Arial,20"
      set linetype 1 lw 2
      set linetype 2 lw 2
      plot $data1 using 1:2 with steps title 'run_1.tsv' noenhanced, \\
           $data2 using 1:2 with steps title 'run_2.tsv' noenhanced
      pause mouse close
      """))

  def test_one_of_multiple_files_missing(self) -> None:
    # Nothing is printed or written, even for the readable file.
    missing = self.dir / "missing.tsv"
    gp = self.dir / "plot.gp"
    code = self.run_main(["-o", str(gp), str(self.tsv_path), str(missing)])
    self.assertEqual(code, 2)
    self.assertIn("cannot read", self.err)
    self.assertEqual(self.out, "")
    self.assertFalse(gp.exists())

  def make_fake_gnuplot(self, status: int = 0) -> dict[str, str]:
    """
    Create a fake "gnuplot" that copies its standard input to
    "stdin.gp" if its only argument is "-", then exits with `status`.
    Return the environment changes that put it first on the PATH.
    """
    bin_dir = self.dir / "bin"
    bin_dir.mkdir()
    gnuplot = bin_dir / "gnuplot"
    gnuplot.write_text(
      "#!/bin/sh\n"
      '[ "$#" = 1 ] && [ "$1" = - ] || exit 99\n'
      f'cat > "{self.dir}/stdin.gp"\n'
      f"exit {status}\n")
    gnuplot.chmod(0o755)
    return {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}

  @unittest.skipUnless(POSIX, "uses a shell script")
  def test_show(self) -> None:
    env = self.make_fake_gnuplot()
    self.assertEqual(self.run_main(["--show", str(self.tsv_path)], env), 0)
    self.assertEqual(self.out, self.summary_line() + self.waiting_line())
    self.assertEqual((self.dir / "stdin.gp").read_text(),
                     self.EXPECTED_SCRIPT)

  @unittest.skipUnless(POSIX, "uses a shell script")
  def test_show_and_output(self) -> None:
    env = self.make_fake_gnuplot()
    gp = self.dir / "plot.gp"
    self.assertEqual(
      self.run_main(["--show", "-o", str(gp), str(self.tsv_path)], env), 0)
    self.assertEqual(self.out, self.summary_line() + self.waiting_line())
    self.assertEqual(gp.read_text(), (self.dir / "stdin.gp").read_text())

  @unittest.skipUnless(POSIX, "uses a shell script")
  def test_show_gnuplot_fails(self) -> None:
    env = self.make_fake_gnuplot(status=3)
    self.assertEqual(self.run_main(["--show", str(self.tsv_path)], env), 2)
    self.assertIn("gnuplot exited with code 3", self.err)

  def test_show_gnuplot_not_found(self) -> None:
    empty_dir = self.dir / "empty"
    empty_dir.mkdir()
    code = self.run_main(["--show", str(self.tsv_path)],
                         {"PATH": str(empty_dir)})
    self.assertEqual(code, 2)
    self.assertIn("cannot run gnuplot", self.err)

  def test_tsv_missing(self) -> None:
    missing = self.dir / "missing.tsv"
    self.assertEqual(self.run_main([str(missing)]), 2)
    self.assertIn("cannot read", self.err)
    self.assertEqual(self.out, "")

  def test_pass_col(self) -> None:
    # The change to pass 2 happens on a rejected row, so it is marked at
    # that row's time with the previously accepted size.
    tsv = self.dir / "passes.tsv"
    tsv.write_text(
      "100.0\tTRUE\t60\n" +
      prow("101.0", "50", "1") +
      prow("102.0", "50", "2", "FALSE") +
      prow("103.0", "40", "2"))
    gp = self.dir / "plot.gp"
    self.assertEqual(
      self.run_main(["--pass-col", str(PASS_COL), "-o", str(gp),
                     str(tsv)]), 0)
    self.assertEqual(self.out,
      f"{tsv} has 4 rows (a=3, m=0).\n")
    self.assertEqual(gp.read_text(), dedent("""
      set title 'Accepted Size vs. Time'
      set xlabel 'reltime (s)'
      set ylabel 'size (bytes)'
      set datafile separator "\\t"
      $data1 << EOD
      0.0\t60
      1.0\t50
      3.0\t40
      EOD
      $pass1 << EOD
      1.0\t50\t1
      2.0\t50\t2
      EOD
      set terminal wxt size 1600,800 font "Arial,20"
      set linetype 1 lw 2
      plot $data1 using 1:2 with steps title 'passes.tsv' noenhanced, \\
           $pass1 using 1:2:3 with labels point pt 7 lt 1 offset char 1,1 notitle noenhanced
      pause mouse close
      """))

  def test_pass_col_absent(self) -> None:
    # No row has column 20, so the script has no pass changes.
    gp = self.dir / "plot.gp"
    self.assertEqual(
      self.run_main(["--pass-col", "20", "-o", str(gp),
                     str(self.tsv_path)]), 0)
    self.assertEqual(gp.read_text(), self.EXPECTED_SCRIPT)

  def test_pass_col_invalid(self) -> None:
    for value in ["0", "-1", "x", "1.5", ""]:
      with self.subTest(value=value):
        self.assertEqual(
          self.run_main(["--pass-col", value, str(self.tsv_path)]), 2)
        self.assertIn("invalid column number", self.err)
    self.assertEqual(self.run_main([str(self.tsv_path), "--pass-col"]), 2)

  def test_usage_errors(self) -> None:
    self.assertEqual(self.run_main([]), 2)
    self.assertEqual(self.run_main(["--bogus", str(self.tsv_path)]), 2)
    self.assertEqual(self.run_main(["-o"]), 2)

  def test_help(self) -> None:
    self.assertEqual(self.run_main(["--help"]), 0)
    self.assertIn("--show", self.out)


if __name__ == "__main__":
  unittest.main()


# EOF
