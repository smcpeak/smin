# check_accept_test.py
"""
Unit tests for check_accept.

If the envvar MANUAL_TEST_PROG is set, then instead of running the unit
tests, running this module directly runs that program as an acceptance
test, using `CheckAccept`, and prints the result.  That is useful for
manually testing the response to Ctrl-C:

  $ MANUAL_TEST_PROG=./some-script python3 check_accept_test.py
"""

from __future__ import annotations

import os
import signal
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from acceptance_test_result import AcceptanceTestResult
from check_accept import CheckAccept


ACCEPT = AcceptanceTestResult.ACCEPT
REJECT = AcceptanceTestResult.REJECT
INTERRUPTED = AcceptanceTestResult.INTERRUPTED

# Signals are only simulated on POSIX systems.
POSIX = os.name == "posix"


def python_command(code: str) -> list[str]:
  """Return a command that runs Python `code` in a new interpreter."""
  return [sys.executable, "-c", code]


class CheckAcceptTest(unittest.TestCase):
  def setUp(self) -> None:
    self.temp_dir = tempfile.TemporaryDirectory()
    self.dir = Path(self.temp_dir.name)
    self.input_file_name = str(self.dir / "input.cc")

  def tearDown(self) -> None:
    self.temp_dir.cleanup()

  def run_code(self, code: str,
               contents: bytes = b"") -> AcceptanceTestResult:
    """Run Python `code` as the acceptance test."""
    checker = CheckAccept(self.input_file_name, python_command(code))
    return checker.run_acceptance_test(contents)

  def test_accept(self) -> None:
    self.assertEqual(self.run_code("pass"), ACCEPT)

  def test_reject(self) -> None:
    self.assertEqual(self.run_code("import sys; sys.exit(1)"), REJECT)

  def test_reject_other_exit_code(self) -> None:
    self.assertEqual(self.run_code("import sys; sys.exit(130)"), REJECT)

  def test_input_written_and_named_by_envvar(self) -> None:
    code = (
      "import os, sys\n"
      "name = os.environ['INPUT']\n"
      f"ok = name == {self.input_file_name!r} and \\\n"
      "  open(name, 'rb').read() == b'int x;\\n'\n"
      "sys.exit(0 if ok else 1)\n")
    self.assertEqual(self.run_code(code, b"int x;\n"), ACCEPT)
    self.assertEqual(Path(self.input_file_name).read_bytes(), b"int x;\n")

  def test_input_overwritten(self) -> None:
    Path(self.input_file_name).write_bytes(b"old contents, longer\n")
    self.run_code("pass", b"new\n")
    self.assertEqual(Path(self.input_file_name).read_bytes(), b"new\n")

  def test_stdin_is_empty(self) -> None:
    code = "import sys; sys.exit(0 if sys.stdin.read() == '' else 1)"
    self.assertEqual(self.run_code(code), ACCEPT)

  @unittest.skipUnless(POSIX, "uses POSIX file identity")
  def test_output_discarded(self) -> None:
    code = (
      "import os, sys\n"
      "null = os.stat(os.devnull)\n"
      "ok = all(os.path.samestat(os.fstat(fd), null) for fd in (1, 2))\n"
      "sys.exit(0 if ok else 1)\n")
    self.assertEqual(self.run_code(code), ACCEPT)

  def test_program_not_found(self) -> None:
    checker = CheckAccept(self.input_file_name,
                          [str(self.dir / "no-such-program")])
    with self.assertRaises(FileNotFoundError):
      checker.run_acceptance_test(b"")

  def test_sigint_handler_restored(self) -> None:
    before = signal.getsignal(signal.SIGINT)
    self.run_code("pass")
    self.assertIs(signal.getsignal(signal.SIGINT), before)

  @unittest.skipUnless(POSIX, "uses POSIX signals")
  def test_killed_by_other_signal(self) -> None:
    code = "import os, signal; os.kill(os.getpid(), signal.SIGTERM)"
    self.assertEqual(self.run_code(code), REJECT)

  @unittest.skipUnless(POSIX, "uses POSIX signals")
  def test_killed_by_sigint(self) -> None:
    # The program dies from SIGINT, although this process did not
    # receive one.
    code = (
      "import os, signal\n"
      "signal.signal(signal.SIGINT, signal.SIG_DFL)\n"
      "os.kill(os.getpid(), signal.SIGINT)\n")
    self.assertEqual(self.run_code(code), INTERRUPTED)

  # ---- Simulated Ctrl-C ----
  #
  # Pressing Ctrl-C sends SIGINT to every process in the terminal's
  # foreground process group.  These tests simulate that by sending it
  # to this process and the program individually, rather than to the
  # process group, which may contain other processes, such as `make`.

  def program_that_waits(self, on_sigint: str) -> str:
    """
    Return the code of a program that sets its SIGINT disposition with
    `on_sigint`, writes its process ID to a file, and then waits for a
    long time, exiting with status 1 if it is not interrupted.
    """
    pid_file = str(self.dir / "pid")
    return (
      "import os, signal, sys, time\n"
      f"{on_sigint}\n"
      f"with open({pid_file + '.tmp'!r}, 'w') as f:\n"
      "  f.write(str(os.getpid()))\n"
      f"os.rename({pid_file + '.tmp'!r}, {pid_file!r})\n"
      "time.sleep(30)\n"
      "sys.exit(1)\n")

  def press_ctrl_c(self, times: int, to_program: bool) -> threading.Thread:
    """
    Start a thread that waits for the program from `program_that_waits`
    to start, and then simulates pressing Ctrl-C `times` times.  If
    `to_program`, SIGINT is sent to the program as well as this process.
    """
    pid_file = self.dir / "pid"

    def run() -> None:
      deadline = time.monotonic() + 10
      while not pid_file.exists():
        if time.monotonic() > deadline:
          return
        time.sleep(0.01)
      child_pid = int(pid_file.read_text())
      for _ in range(times):
        if to_program:
          os.kill(child_pid, signal.SIGINT)
        os.kill(os.getpid(), signal.SIGINT)
        time.sleep(0.1)

    thread = threading.Thread(target=run)
    thread.start()
    return thread

  def check_ctrl_c(self, on_sigint: str, times: int,
                   to_program: bool = True) -> None:
    """Check that a simulated Ctrl-C yields INTERRUPTED promptly."""
    thread = self.press_ctrl_c(times, to_program)
    start: float = time.monotonic()
    result = self.run_code(self.program_that_waits(on_sigint))
    elapsed: float = time.monotonic() - start
    thread.join()

    self.assertEqual(result, INTERRUPTED)
    self.assertLess(elapsed, 10)       # Less than 10 seconds.

  @unittest.skipUnless(POSIX, "uses POSIX signals")
  def test_ctrl_c_program_dies(self) -> None:
    self.check_ctrl_c(
      "signal.signal(signal.SIGINT, signal.SIG_DFL)", times=1)

  @unittest.skipUnless(POSIX, "uses POSIX signals")
  def test_ctrl_c_program_exits_normally(self) -> None:
    # Even though the program exits with status 0, the Ctrl-C means the
    # result is INTERRUPTED.
    self.check_ctrl_c(
      "signal.signal(signal.SIGINT, lambda s, f: os._exit(0))", times=1)

  @unittest.skipUnless(POSIX, "uses POSIX signals")
  def test_second_ctrl_c_kills_program(self) -> None:
    # The program ignores SIGINT, so the first Ctrl-C does not stop it,
    # but the second one kills it.
    self.check_ctrl_c(
      "signal.signal(signal.SIGINT, signal.SIG_IGN)", times=2)


def manual_test(program: str) -> None:
  """Run `program` as an acceptance test and print the result."""
  with tempfile.TemporaryDirectory() as temp_dir:
    input_file_name = str(Path(temp_dir) / "input.txt")
    checker = CheckAccept(input_file_name, [program])
    print(f"Running {program!r} with INPUT={input_file_name!r} ...",
          flush=True)
    result = checker.run_acceptance_test(b"manual test input\n")
    print(f"Result: {result.name}")


def main() -> None:
  program = os.environ.get("MANUAL_TEST_PROG")
  if program:
    manual_test(program)
  else:
    unittest.main()


if __name__ == "__main__":
  main()


# EOF
