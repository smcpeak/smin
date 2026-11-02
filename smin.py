#!/usr/bin/env python3
# smin.py
"""
Structural minimizer command line driver.

Usage:

  smin.py [options] test_program [test_prog_args...] -- input_file

Options:

  --max-passes N

    Limit the number of passes to at most N, limiting the removal
    granularity.  Without this, minimization runs as many passes as
    needed to eventually try removing individual tokens.

  --ma2

    Use Minimization Algorithm 2 (MA2) as described in the spec.

See spec in minimization-algorithm.txt.
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
from minimizer import Minimizer
from start_report import TestStartReport
from lang_cpp import CPPLanguage
from language import Language


# Exit status for a run that stopped because of Ctrl-C, following the
# shell convention of 128 + SIGINT.
EXIT_INTERRUPTED = 130


class _Console:
  """Print progress messages to stdout."""

  # True if the last thing printed ended with a newline (or nothing has
  # been printed yet).
  at_line_start: bool

  # Previously printed start report, if any.
  prev_ts_report: Optional[TestStartReport]

  def __init__(self) -> None:
    self.at_line_start = True
    self.prev_ts_report = None

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
    # If we are beginning a new pass, print a blank line.  Otherwise it
    # is unnecessarily difficult to spot the transition by eye.
    if (self.prev_ts_report is not None and
        self.prev_ts_report.pass_num < report.pass_num):
      self.write("\n")

    self.write(report.to_console_string())
    self.prev_ts_report = report

  def report_test_finished(
    self,
    result: AcceptanceTestResult,
    memoized: bool,
  ) -> None:
    if result == AcceptanceTestResult.ACCEPT:
      verdict = " ACCEPTED"
      if self.prev_ts_report is not None:
        n: int = self.prev_ts_report.removed_tok_count
        verdict += f" (removed {n})"

    elif result == AcceptanceTestResult.REJECT:
      verdict = " rejected"

    else:
      verdict = " INTERRUPTED"

    self.write(verdict + (" (memo)" if memoized else "") + "\n")


def parse_command_line(argv: list[str]) -> argparse.Namespace:
  """
  Parse the command line arguments `argv` (not including the program
  name).

  On error, exit with status 2.  (ArgumentParser.error does that.)
  """

  parser = argparse.ArgumentParser(
    prog="smin.py",
    usage="%(prog)s [options] test_program [args...] -- input_file",
    description="Minimize input_file, preserving the property that "
                "test_program accepts it.",
    epilog="""
      The test program indicates acceptance by exiting with code 0;
      anything else means reject.  It is run with the INPUT envvar set
      to <input_file> (the same string as was passed on the command
      line).  INPUT_BEST is set to "<input_file>.best", which the
      minimizer maintains as the most recently accepted input.
      INPUT_BEST is set, but the file does not exist, on the very first
      invocation of the acceptance test.  SMIN_PROGRESS is set to a
      string that compactly describes where we are in the minimization
      process (it is part of the string that smin prints to the
      console).  CHANGED_BYTE_RANGE is set to "A-B", where the candidate
      was produced from INPUT_BEST by modifying the byte range [A,B).
    """)

  parser.add_argument(
    "--max-passes", type=_positive_int, metavar="N",
    help="""
      Make at most N passes, limiting how finely the input is divided
      when trying removals.
    """)

  parser.add_argument(
    "--ma2", action="store_true",
    help="""
      Use Minimization Algorithm 2 (MA2) rather than the default, MA1.
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


def _positive_int(s: str) -> int:
  """Parse `s` as a positive integer, for argparse."""
  try:
    n = int(s)
  except ValueError:
    n = 0
  if n < 1:
    raise argparse.ArgumentTypeError(f"not a positive integer: {s!r}")
  return n


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

  Exit codes:

      0: Successful completed minimization.

      1: Initial input was rejected by the acceptance test.

      2: Ordinary error: input file not found, acceptance test could not
         be executed, command line syntax error, etc.

      4: Internal error; this program (smin) has a bug.

    130: Minimization was interrupted by SIGINT / Ctrl-C.
  """

  # Seconds since an arbitrary epoch.
  start_time: float = time.monotonic()

  console = _Console()

  args: argparse.Namespace = parse_command_line(argv)
  fname: str = args.input_file
  test_command: list[str] = args.test_command

  # All language-specific knowledge comes from this object.  (Later we
  # might add an option to choose the language.)
  language: Language = CPPLanguage()

  # ---- Startup ----
  try:
    with open(fname, "rb") as f:
      data = f.read()
  except OSError as e:
    print(f"smin.py: error: cannot read {fname!r}: {e.strerror}",
          file=sys.stderr)
    return 2

  tree = build_tree(language.make_tokenizer().tokenize(data))
  orig_tok_count = sum(1 for _ in tree.tokens())

  console.line(
    f"Initial {fname} has {orig_tok_count} tokens, {len(data)} bytes, "
    f"and a maximum tree depth of {tree.depth()}.")

  if tree.text() != data:
    print(f"smin.py: internal error: rendering the token tree of "
          f"{fname!r} does not reproduce its contents", file=sys.stderr)
    return 4

  checker = CheckAccept(fname, test_command)

  # Once created, this holds the most recently accepted input.
  minimizer: Optional[Minimizer] = None

  try:
    best_existed: bool = os.path.exists(checker.best_file_name)

    # Remove a left-over .best file since it's unrelated to the current
    # minimization attempt.
    if best_existed:
      os.remove(checker.best_file_name)

    initial_test_succeeded: bool = False
    try:
      console.write(
        f"Checking {test_command[0]} on initial {fname} ... ")
      try:
        result = checker.run_acceptance_test(data, None)
      except OSError as e:
        console.end_line()
        print(f"smin.py: error: cannot run {test_command[0]!r}: "
              f"{e.strerror}", file=sys.stderr)
        return 2

      if result == AcceptanceTestResult.INTERRUPTED:
        console.write("INTERRUPTED\n")
        raise KeyboardInterrupt()
      if result == AcceptanceTestResult.REJECT:
        console.write("REJECTED\n")
        console.line("Stopping because the initial input was rejected.")
        return 1
      console.write("accepted\n")
      initial_test_succeeded = True

    finally:
      if best_existed and not initial_test_succeeded:
        # Acknowledge having removing the .best file.
        console.line(f"Note: I removed {checker.best_file_name}.")

    console.line(
      f"Will continuously update {checker.best_file_name}" +
      (" (which was overwritten)." if best_existed else "."))

    backup = fname + ".bak"
    bak_was_overwritten: bool = os.path.exists(backup)
    shutil.copyfile(fname, backup)
    console.line(
      f"Copied {fname} to {backup}" +
      (" (which was overwritten)." if bak_was_overwritten else "."))

    # ---- Minimization ----
    minimizer = Minimizer(
      tree,
      language.get_non_trivial_replacement_func(),
      checker.run_acceptance_test,
      console.report_test_starting,
      console.report_test_finished,
      args.max_passes,
      args.ma2)
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

  # Emit a blank line after the final pass for uniformity with the other
  # passes.
  console.line("")

  # There is a quirk here that shows up with "./t_accept.py --reject"
  # and similar situations: if the whitespace at the end of the file is
  # a single newline (which is typical), then that becomes its own
  # token, which the core minimizer algorithm will attempt to remove.
  # However, a newline is then added by the candidate renderer, since we
  # don't want to test inputs without final newlines if the original
  # wasn't that way.  Even with --reject or similar, the candidate with
  # the final newline "removed" gets accepted because (after rendering)
  # it exactly matches the original input and hence is in the
  # memoization table.  Later, the "Reduced file" message claims a
  # single token was removed, even though the file contents are
  # unchanged.  For now, I just note the oddity.
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
