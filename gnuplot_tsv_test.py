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

from gnuplot_tsv import main, make_script, parse_tsv
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


class ParseTsvTest(unittest.TestCase):
  def test_empty(self) -> None:
    self.assertEqual(parse_tsv(""), ([], 0))

  def test_well_formed(self) -> None:
    text = (row("100.5", "10") +
            row("100.75", "6") +
            row("101.000000001", "6"))
    self.assertEqual(parse_tsv(text), ([
      (Decimal(0), 10),
      (Decimal("0.25"), 6),
      # The difference is exact.
      (Decimal("0.500000001"), 6),
    ], 3))

  def test_rejected_rows_ignored(self) -> None:
    # Only a verdict of exactly "TRUE" is accepted.  The reltime is
    # measured from the first accepted row, and the ignored rows still
    # count toward the total.
    text = (row("99.0", "12", "FALSE") +
            row("100.0", "10") +
            row("100.5", "8", "FALSE") +
            row("101.0", "9", "true") +
            row("101.5", "9", "maybe") +
            row("102.0", "7"))
    self.assertEqual(parse_tsv(text),
                     ([(Decimal(0), 10), (Decimal(2), 7)], 6))

  def test_integer_timestamp(self) -> None:
    self.assertEqual(parse_tsv(row("7", "1") + row("9", "0")),
                     ([(Decimal(0), 1), (Decimal(2), 0)], 2))

  def test_malformed_rows_ignored(self) -> None:
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

    # The reltime is measured from the first well-formed row, and the
    # ignored rows still count toward the total.
    self.assertEqual(parse_tsv(text),
                     ([(Decimal(0), 8), (Decimal(1), 7)], 10))

  def test_other_columns_not_validated(self) -> None:
    text = "5.0\tTRUE\t3\tN\tS\tP\tPm\tF\tR\n"
    self.assertEqual(parse_tsv(text), ([(Decimal(0), 3)], 1))

  def test_three_fields_enough(self) -> None:
    # The initial test's row has no progress fields.
    self.assertEqual(parse_tsv("5.0\tTRUE\t30\n" + row("6.0", "20")),
                     ([(Decimal(0), 30), (Decimal(1), 20)], 2))

  def test_extra_fields_allowed(self) -> None:
    self.assertEqual(parse_tsv(row("5.0", "3").rstrip("\n") + "\textra\n"),
                     ([(Decimal(0), 3)], 1))

  def test_no_final_newline(self) -> None:
    self.assertEqual(parse_tsv(row("5.0", "3") + row("6.0", "2").rstrip()),
                     ([(Decimal(0), 3), (Decimal(1), 2)], 2))


class MakeScriptTest(unittest.TestCase):
  def test_one_dataset(self) -> None:
    script = make_script([("log.tsv", [(Decimal(0), 10),
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
      ("a.tsv", [(Decimal(0), 10)]),
      ("b.tsv", []),
      ("c.tsv", [(Decimal(0), 7), (Decimal(3), 5)]),
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

  def test_label_quoted(self) -> None:
    script = make_script([("it's.tsv", [])])
    self.assertIn(" title 'it''s.tsv' noenhanced\n", script)


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
    return (f"{self.tsv_path} has 2 rows of well-formed data out of "
            f"3 rows in total.\n")

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
      f"{other} has 3 rows of well-formed data out of 3 rows in total.\n")

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
