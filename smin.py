#!/usr/bin/env python3
# smin.py
"""
Structural minimizer command line driver.

Usage:

  smin.py [options] test_program [test_prog_args...] -- input_file

See minimization-algorithm.txt, especially "Startup" and "Termination".
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import sys
import time
from typing import Optional

from acceptance_test_result import AcceptanceTestResult
from build_tree import build_tree
from check_accept import CheckAccept
from minimizer import Minimizer, TestStartReport
from token_tree import TTNode
from tokenize_cpp import tokenize_cpp


# Exit status for a run that stopped because of Ctrl-C, following the
# shell convention of 128 + SIGINT.
EXIT_INTERRUPTED = 130


class _Console:
  """Print progress messages to stdout."""

  # True if the last thing printed ended with a newline (or nothing has
  # been printed yet).
  at_line_start: bool

  def __init__(self) -> None:
    self.at_line_start = True

  def write(self, s: str) -> None:
    """Print `s` and flush, so partial lines are visible immediately."""
    if s:
      sys.stdout.write(s)
      sys.stdout.flush()
      self.at_line_start = s.endswith("\n")

  def end_line(self) -> None:
    """End the current line if it is partial."""
    if not self.at_line_start:
      self.write("\n")

  def line(self, s: str) -> None:
    """Print `s` on its own line, ending any partial line first."""
    self.end_line()
    self.write(s + "\n")

  def report_test_starting(self, report: TestStartReport) -> None:
    self.write(report.to_console_string())

  def report_test_finished(self, result: AcceptanceTestResult) -> None:
    if result == AcceptanceTestResult.ACCEPT:
      self.write(" ACCEPTED\n")
    elif result == AcceptanceTestResult.REJECT:
      self.write(" rejected\n")
    else:
      self.write(" INTERRUPTED\n")


def parse_command_line(argv: list[str]) -> argparse.Namespace:
  """
  Parse the command line arguments `argv` (not including the program
  name).  The result has attributes `test_command` (the test program and
  its arguments) and `input_file`.  On error, exit with status 2.
  """

  parser = argparse.ArgumentParser(
    prog="smin.py",
    usage="%(prog)s [options] test_program [args...] -- input_file",
    description="Minimize input_file, preserving the property that "
                "test_program accepts it.",
    epilog="""
      For convenience, the test program is run with the INPUT
      environment variable set to input_file.  An exit status of 0 means
      the candidate is accepted.
    """)

  # The test command, separator, and input file are all collected into
  # one list, and split below.  (With separate positional arguments,
  # argparse would discard a "--" immediately after `test_program`.)
  parser.add_argument(
    "cmd_and_input", nargs=argparse.REMAINDER,
    metavar="test_program [args...] -- input_file",
    help="""
      Program (and its arguments) to run to test a candidate input,
      then the input file to minimize (which is copied to a .bak file
      beforehand).
    """)

  args = parser.parse_args(argv)
  cmd_and_input: list[str] = args.cmd_and_input

  if cmd_and_input.count("--") != 1:
    parser.error('there must be exactly one "--" argument')
  sep = cmd_and_input.index("--")
  if sep != len(cmd_and_input) - 2:
    parser.error('"--" must be followed by exactly one argument, '
                 'input_file')
  if sep == 0:
    parser.error('test_program is missing before "--"')

  args.test_command = cmd_and_input[:sep]
  args.input_file = cmd_and_input[-1]
  return args


def tree_depth(node: TTNode) -> int:
  """
  Return the number of edges on the longest path from `node` down to a
  leaf.
  """
  if not node.children:
    return 0
  return 1 + max(tree_depth(child) for child in node.children)


def cpp_non_trivial_replacement(node: TTNode) -> Optional[bytes]:
  """
  The `NTReplacementFunc` for C++: a brace group, such as a function
  body, can be replaced with ";".
  """
  if node.delim_group:
    opener = node.children[0].token
    assert opener is not None
    if opener.delimiter_kind == -3:
      return b";"
  return None


def format_elapsed_time(seconds: float) -> str:
  """Format `seconds` as D:HH:MM:SS, truncating fractional seconds."""
  minutes, secs = divmod(int(seconds), 60)
  hours, minutes = divmod(minutes, 60)
  days, hours = divmod(hours, 24)
  return f"{days}:{hours:02d}:{minutes:02d}:{secs:02d}"


def main(argv: list[str]) -> int:
  """
  Run the minimizer with command line arguments `argv` (not including
  the program name), and return the exit status.
  """

  start_time = time.monotonic()
  console = _Console()

  args = parse_command_line(argv)
  fname: str = args.input_file
  test_command: list[str] = args.test_command

  # ---- Startup ----
  try:
    with open(fname, "rb") as f:
      data = f.read()
  except OSError as e:
    print(f"smin.py: error: cannot read {fname!r}: {e.strerror}",
          file=sys.stderr)
    return 1

  tree = build_tree(tokenize_cpp(data))
  orig_tok_count = sum(1 for _ in tree.tokens())

  console.line(
    f"Initial {fname} has {orig_tok_count} tokens, {len(data)} bytes, "
    f"and a maximum tree depth of {tree_depth(tree)}.")

  if tree.text() != data:
    print(f"smin.py: internal error: rendering the token tree of "
          f"{fname!r} does not reproduce its contents", file=sys.stderr)
    return 1

  checker = CheckAccept(fname, test_command)

  # Once created, this holds the most recently accepted input.
  minimizer: Optional[Minimizer] = None

  try:
    console.write(
      f"Checking {test_command[0]} on initial {fname} ... ")
    try:
      result = checker.run_acceptance_test(data)
    except OSError as e:
      console.end_line()
      print(f"smin.py: error: cannot run {test_command[0]!r}: "
            f"{e.strerror}", file=sys.stderr)
      return 1

    if result == AcceptanceTestResult.INTERRUPTED:
      console.write("INTERRUPTED\n")
      raise KeyboardInterrupt()
    if result == AcceptanceTestResult.REJECT:
      console.write("REJECTED\n")
      console.line("Stopping because the initial input was rejected.")
      return 1
    console.write("accepted\n")

    backup = fname + ".bak"
    overwritten = os.path.exists(backup)
    shutil.copyfile(fname, backup)
    console.line(
      f"Copied {fname} to {backup}" +
      (" (which was overwritten)." if overwritten else "."))

    # ---- Minimization ----
    minimizer = Minimizer(
      tree,
      cpp_non_trivial_replacement,
      checker.run_acceptance_test,
      console.report_test_starting,
      console.report_test_finished)
    result = minimizer.run_minimizer()

  except KeyboardInterrupt:
    result = AcceptanceTestResult.INTERRUPTED

  except BaseException:
    # Leave an accepted input in the file before propagating the error.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    _write_file(fname, data if minimizer is None
                       else minimizer.render_candidate({}))
    console.end_line()
    raise

  # ---- Termination ----

  # From here on, Ctrl-C is ignored so that it cannot interrupt writing
  # the final result.
  signal.signal(signal.SIGINT, signal.SIG_IGN)

  if minimizer is None:
    # Interrupted before minimization started.  The initial test may
    # have rewritten the file, so restore it.
    final_data, final_tok_count = data, orig_tok_count
  else:
    # This uses `render_candidate` rather than `get_minimized_test_input`
    # since the latter requires that `run_minimizer` has been invoked,
    # which may not be the case after Ctrl-C.
    final_data = minimizer.render_candidate({})
    final_tok_count = minimizer.current_tok_count()

  _write_file(fname, final_data)

  interrupted = result == AcceptanceTestResult.INTERRUPTED
  if interrupted:
    console.line("Stopping early due to Ctrl-C.")

  console.line(
    f"Reduced file {fname} from {orig_tok_count} tokens "
    f"({len(data)} bytes) to {final_tok_count} tokens "
    f"({len(final_data)} bytes).")
  console.line(
    f"Elapsed time (D:HH:MM:SS): "
    f"{format_elapsed_time(time.monotonic() - start_time)}")

  return EXIT_INTERRUPTED if interrupted else 0


def _write_file(fname: str, contents: bytes) -> None:
  with open(fname, "wb") as f:
    f.write(contents)


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))


# EOF
