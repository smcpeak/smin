# smin_test.py
"""
Unit tests for smin.
"""

from __future__ import annotations

import contextlib
import io
import os
import signal
import sys
import tempfile
import unittest
from pathlib import Path

from smin import (
  EXIT_INTERRUPTED,
  format_elapsed_time,
  main,
  parse_command_line,
)


# Signals are only simulated on POSIX systems.
POSIX = os.name == "posix"


class ParseCommandLineTest(unittest.TestCase):
  def check_error(self, argv: list[str]) -> None:
    with contextlib.redirect_stderr(io.StringIO()):
      with self.assertRaises(SystemExit) as cm:
        parse_command_line(argv)
    self.assertEqual(cm.exception.code, 2)

  def test_program_only(self) -> None:
    args = parse_command_line(["./test.sh", "--", "in.cc"])
    self.assertEqual(args.test_command, ["./test.sh"])
    self.assertEqual(args.input_file, "in.cc")

  def test_program_args(self) -> None:
    args = parse_command_line(["./test.sh", "-v", "x", "--", "in.cc"])
    self.assertEqual(args.test_command, ["./test.sh", "-v", "x"])
    self.assertEqual(args.input_file, "in.cc")

  def test_program_option_like_args(self) -> None:
    args = parse_command_line(["./test.sh", "-h", "--x", "--", "in.cc"])
    self.assertEqual(args.test_command, ["./test.sh", "-h", "--x"])
    self.assertEqual(args.input_file, "in.cc")

  def test_help(self) -> None:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
      with self.assertRaises(SystemExit) as cm:
        parse_command_line(["--help"])
    self.assertEqual(cm.exception.code, 0)
    self.assertIn("usage: smin.py", out.getvalue())

  def test_two_separators(self) -> None:
    self.check_error(["grep", "-q", "--", "x", "--", "in.cc"])

  def test_leading_separator(self) -> None:
    self.check_error(["--", "./test.sh", "--", "in.cc"])

  def test_separator_not_second_to_last(self) -> None:
    self.check_error(["./test.sh", "--", "in.cc", "extra"])

  def test_missing_separator(self) -> None:
    self.check_error(["./test.sh", "in.cc"])

  def test_missing_input_file(self) -> None:
    self.check_error(["./test.sh", "--"])

  def test_missing_program(self) -> None:
    self.check_error(["--", "in.cc"])

  def test_empty(self) -> None:
    self.check_error([])


class HelperTest(unittest.TestCase):
  def test_format_elapsed_time(self) -> None:
    self.assertEqual(format_elapsed_time(0), "0:00:00:00")
    self.assertEqual(format_elapsed_time(59.9), "0:00:00:59")
    self.assertEqual(format_elapsed_time(3723), "0:01:02:03")
    self.assertEqual(format_elapsed_time(2*86400 + 5), "2:00:00:05")


class MainTest(unittest.TestCase):
  def setUp(self) -> None:
    self.temp_dir = tempfile.TemporaryDirectory()
    self.dir = Path(self.temp_dir.name)
    self.input_path = self.dir / "input.cc"
    self.backup_path = self.dir / "input.cc.bak"
    self.best_path = self.dir / "input.cc.best"

    # `main` ignores SIGINT once it starts terminating.
    self.old_sigint = signal.getsignal(signal.SIGINT)

  def tearDown(self) -> None:
    signal.signal(signal.SIGINT, self.old_sigint)
    self.temp_dir.cleanup()

  def run_main(self, code: str) -> tuple[int, str, str]:
    """
    Run `main` with Python `code` as the test program, returning the
    exit status, stdout, and stderr.
    """
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
      status = main(
        [sys.executable, "-c", code, "--", str(self.input_path)])
    return status, out.getvalue(), err.getvalue()

  # Accept an input that contains "keep".
  KEEP_CODE = (
    "import os, sys\n"
    "sys.exit(0 if b'keep' in open(os.environ['INPUT'], 'rb').read() "
    "else 1)\n")

  def test_minimize(self) -> None:
    self.input_path.write_bytes(b"int a;\nint keep;\nint b;\n")
    status, out, err = self.run_main(self.KEEP_CODE)
    self.assertEqual(status, 0)
    self.assertEqual(err, "")
    self.assertEqual(self.input_path.read_bytes(), b"\nkeep\n")
    self.assertEqual(self.backup_path.read_bytes(),
                     b"int a;\nint keep;\nint b;\n")
    self.assertEqual(self.best_path.read_bytes(), b"\nkeep\n")
    self.assertFalse(Path(f"{self.best_path}.tmp").exists())

    lines = out.splitlines()
    fname = str(self.input_path)
    self.assertEqual(lines[0],
      f"Initial {fname} has 10 tokens, 24 bytes, "
      f"and a maximum tree depth of 2.")
    self.assertEqual(lines[1],
      f"Checking {sys.executable} on initial {fname} ... accepted")
    self.assertEqual(lines[2], f"Will continuously update {fname}.best.")
    self.assertEqual(lines[3], f"Copied {fname} to {fname}.bak.")
    self.assertTrue(lines[4].startswith("N=000001 S=10 "))
    self.assertEqual(lines[-2],
      f"Reduced file {fname} from 10 tokens (24 bytes) "
      f"to 1 tokens (6 bytes).")
    self.assertRegex(lines[-1], r"^Elapsed time \(D:HH:MM:SS\): 0:00:00:\d\d$")

    # Every test line has a result (aside from blank lines that separate
    # passes).
    for line in lines[4:-2]:
      if line != "":
        self.assertRegex(line,
          r"^N=\d{6} .* \.\.\. (rejected|ACCEPTED)( \(memo\))?$")

  def test_backup_overwritten(self) -> None:
    self.input_path.write_bytes(b"keep\n")
    self.backup_path.write_bytes(b"old backup\n")
    status, out, _ = self.run_main(self.KEEP_CODE)
    self.assertEqual(status, 0)
    self.assertIn(f"Copied {self.input_path} to {self.backup_path} "
                  f"(which was overwritten).\n", out)
    self.assertEqual(self.backup_path.read_bytes(), b"keep\n")

  def test_best_overwritten(self) -> None:
    self.input_path.write_bytes(b"keep\n")
    self.best_path.write_bytes(b"old best\n")
    status, out, _ = self.run_main(self.KEEP_CODE)
    self.assertEqual(status, 0)
    self.assertIn(f"Will continuously update {self.best_path} "
                  f"(which was overwritten).\n", out)
    self.assertEqual(self.best_path.read_bytes(), b"keep\n")

  def test_initial_input_rejected(self) -> None:
    self.input_path.write_bytes(b"int a;\n")
    status, out, _ = self.run_main(self.KEEP_CODE)
    self.assertEqual(status, 1)
    self.assertTrue(out.endswith(
      "... REJECTED\n"
      "Stopping because the initial input was rejected.\n"))
    self.assertEqual(self.input_path.read_bytes(), b"int a;\n")
    self.assertFalse(self.backup_path.exists())

  def test_input_file_missing(self) -> None:
    status, out, err = self.run_main(self.KEEP_CODE)
    self.assertEqual(status, 2)
    self.assertEqual(out, "")
    self.assertIn("cannot read", err)

  def test_program_not_found(self) -> None:
    self.input_path.write_bytes(b"keep\n")
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
      status = main([str(self.dir / "no-such-program"), "--",
                     str(self.input_path)])
    self.assertEqual(status, 2)
    self.assertIn("cannot run", err.getvalue())
    self.assertEqual(self.input_path.read_bytes(), b"keep\n")

  def ctrl_c_code(self, on_invocation: int) -> str:
    """
    Return the code of a test program that behaves like `KEEP_CODE`,
    except that on invocation number `on_invocation` (counting the
    initial test as 1), it simulates Ctrl-C by sending SIGINT to its
    parent (the minimizer) and to itself.
    """
    count_file = str(self.dir / "count")
    return (
      "import os, signal, sys\n"
      f"name = {count_file!r}\n"
      "n = int(open(name).read()) + 1 if os.path.exists(name) else 1\n"
      "open(name, 'w').write(str(n))\n"
      f"if n == {on_invocation}:\n"
      "  signal.signal(signal.SIGINT, signal.SIG_DFL)\n"
      "  os.kill(os.getppid(), signal.SIGINT)\n"
      "  os.kill(os.getpid(), signal.SIGINT)\n"
      + self.KEEP_CODE)

  @unittest.skipUnless(POSIX, "uses POSIX signals")
  def test_ctrl_c_during_minimization(self) -> None:
    self.input_path.write_bytes(b"int a;\nint keep;\nint b;\n")
    # Test N=2, removing the final newline, is a memo hit, since the
    # newline is restored.  Test N=3 (invocation 3) removes "int b;" and
    # is accepted.  Test N=4 (invocation 4) is interrupted.
    status, out, _ = self.run_main(self.ctrl_c_code(4))
    self.assertEqual(status, EXIT_INTERRUPTED)
    self.assertEqual(self.input_path.read_bytes(), b"int a;\nint keep;\n")
    self.assertEqual(self.best_path.read_bytes(), b"int a;\nint keep;\n")

    lines = out.splitlines()
    self.assertRegex(lines[-6], r"^N=000003 .* ACCEPTED$")
    self.assertRegex(lines[-5], r"^N=000004 .* INTERRUPTED$")
    self.assertEqual(lines[-4], "Stopping early due to Ctrl-C.")
    self.assertEqual(lines[-3], "")
    self.assertEqual(lines[-2],
      f"Reduced file {self.input_path} from 10 tokens (24 bytes) "
      f"to 6 tokens (17 bytes).")

  @unittest.skipUnless(POSIX, "uses POSIX signals")
  def test_ctrl_c_during_initial_test(self) -> None:
    self.input_path.write_bytes(b"int keep;\n")
    status, out, _ = self.run_main(self.ctrl_c_code(1))
    self.assertEqual(status, EXIT_INTERRUPTED)
    self.assertEqual(self.input_path.read_bytes(), b"int keep;\n")
    self.assertFalse(self.backup_path.exists())
    self.assertFalse(self.best_path.exists())
    self.assertIn(
      "... INTERRUPTED\n"
      "Stopping early due to Ctrl-C.\n"
      "\n"
      f"Reduced file {self.input_path} from 4 tokens (10 bytes) "
      f"to 4 tokens (10 bytes).\n", out)


if __name__ == "__main__":
  unittest.main()


# EOF
