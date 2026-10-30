# check_accept.py
"""
CheckAccept class.
"""

from __future__ import annotations

import os
import signal
import subprocess
from dataclasses import dataclass
from types import FrameType

from acceptance_test_result import AcceptanceTestResult


@dataclass
class CheckAccept:
  """
  Manage the invocation of the the acceptance program for the minimizer.
  """

  # The name of the file that holds the candidate input file to be
  # tested for acceptance.  This name comes from the command line, and
  # is typically a relative file name, relative to the current working
  # directory.  It is a string (rather than a Path) in part because it
  # is passed to the acceptance test via an envvar, and I want to pass
  # along the exact string that the user originally provided.
  input_file_name: str

  # The command (program, then arguments) to invoke the acceptance test.
  # The list comes from the command line, and we simply pass it along
  # unchanged.
  acceptance_command: list[str]


  def run_acceptance_test(
    self,
    input_contents: bytes,
  ) -> AcceptanceTestResult:
    """
    First, write `input_contents` to `input_file_name` (any exception
    due to that will propagate to the caller).

    Then, in the current directory, invoke `acceptance_command`.  It is
    executed with envvar "INPUT" added to the environment with value
    `input_file_name`.  Its stdin reads from, and its stdout and stderr
    write to, the platform equivalent of /dev/null.  The former is to
    ensure it will not hang if it tries to read user input (the
    acceptance test should be entirely non-interactive), and the latter
    is to avoid disrupting the minimizer progress reports it writes to
    the console.

    This function waits for the spawned program to terminate.  It
    returns ACCEPT if the exit code is 0, INTERRUPTED if it was
    interrupted by Ctrl-C, and REJECT otherwise (including other forms
    of death by signal).

    The signature of this function follows that of `AcceptanceTestFunc`
    in the `minimizer` module.

    Ctrl-C is detected by temporarily replacing the SIGINT handler of
    this process while the program runs, so this must be called from
    the main thread.  When the user presses Ctrl-C, the terminal sends
    SIGINT to both this process and the program, so the program will
    typically terminate soon after, at which point we report
    INTERRUPTED regardless of its exit status.  (This handles test
    programs, such as shell scripts, that exit normally in response to
    SIGINT.)  If the user presses Ctrl-C a second time while waiting,
    the program is killed, in case it ignores SIGINT.

    The current SIGINT handler must have been installed by Python
    (otherwise we would not be able to restore it).

    The acceptance test program invocation is counted as INTERRUPTED if
    it dies from SIGINT, even if this process did not receive one.

    If the program cannot be started (for example, because it does not
    exist), the exception from `subprocess.Popen` propagates.
    """

    # Get the previous SIGINT handler, and insist it is something we can
    # restore.
    old_handler = signal.getsignal(signal.SIGINT)
    assert old_handler != None, "SIGINT handler was not installed by Python"

    with open(self.input_file_name, "wb") as f:
      f.write(input_contents)

    env = dict(os.environ)
    env["INPUT"] = self.input_file_name

    # Number of times SIGINT has been received while the program runs.
    interrupt_count = 0

    proc: subprocess.Popen[bytes] | None = None

    def on_sigint(signum: int, frame: FrameType | None) -> None:
      nonlocal interrupt_count
      interrupt_count += 1
      if interrupt_count >= 2 and proc is not None:
        proc.kill()

    # The handler is installed before starting the program so there is
    # no window where Ctrl-C would raise KeyboardInterrupt and orphan
    # it.  The program does not inherit the handler, since `exec`
    # resets caught signals to their default disposition.
    old_handler2 = signal.signal(signal.SIGINT, on_sigint)
    assert old_handler2 == old_handler      # Just to be sure.
    try:
      proc = subprocess.Popen(
        self.acceptance_command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
      )
      returncode = proc.wait()
    finally:
      signal.signal(signal.SIGINT, old_handler)

    if interrupt_count > 0 or returncode == -signal.SIGINT:
      return AcceptanceTestResult.INTERRUPTED
    if returncode == 0:
      return AcceptanceTestResult.ACCEPT
    return AcceptanceTestResult.REJECT


# EOF
