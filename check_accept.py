# check_accept.py
"""
CheckAccept class.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    First, write `input_contents` to `input_file_name`.

    Then, in the current directory, invoke `acceptance_command`.  It is
    executed with envvar "INPUT" added to the environment with value
    `input_file_name`.  It also has its stdin closed, and its stdout and
    stderr redirected to the platform equivalent of /dev/null.

    This function waits for the spawned program to terminate.  It
    returns ACCEPT if the exit code is 0, INTERRUPTED if it was
    interrupted by Ctrl-C, and REJECT otherwise (including other forms
    of death by signal).

    The signature of this function follows that of `AcceptanceTestFunc`
    in the `minimizer` module.
    """

    # TODO: Implement this.
    return AcceptanceTestResult.ACCEPT


# EOF
