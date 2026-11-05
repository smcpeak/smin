#!/usr/bin/env python3
# run_bm.py
"""
Run a minimizer on one of the benchmarks.

Usage:

  ./run_bm.py <minimizer> <benchmarkdir>

The results go into out/<benchmark>/<minimizer>, relative to the current
directory, replacing any prior run there.

The exit status is that of the minimizer, or 2 for a usage error, or
that of the first preparatory step to fail.
"""

from __future__ import annotations

import os
import shlex
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from types import FrameType
from typing import Optional


# Directories containing this script and the minimizer sources.
BM_DIR: Path = Path(__file__).resolve().parent
REPO_DIR: Path = BM_DIR.parent

# Exit status for a usage error.
EXIT_USAGE = 2

# Exit status for a failed step that does not have its own status.
EXIT_FAILURE = 1

# Exit statuses for a program that could not be started, following the
# shell convention.
EXIT_CANNOT_EXECUTE = 126
EXIT_NOT_FOUND = 127

# The test script and the input it checks, within a run directory.
TEST_SH = "./test.sh"
INPUT = "input"

# Map from minimizer name to the command that runs it in a run directory.
_SMIN_PY: str = str(REPO_DIR / "smin.py")
MINIMIZER_COMMANDS: dict[str, list[str]] = {
  "smin":     [_SMIN_PY, TEST_SH, "--", INPUT],
  "smin-ma2": [_SMIN_PY, "--ma2", TEST_SH, "--", INPUT],
  "smin-hdd": [_SMIN_PY, "--hdd", TEST_SH, "--", INPUT],
  "delta":    ["multimultidelta", TEST_SH, INPUT],

  # --n 1 causes these to run sequentially.
  "creduce":  ["creduce", "--n", "1", TEST_SH, INPUT],
  "cvise":    ["cvise", "--n", "1", TEST_SH, INPUT],
}


def usage_text() -> str:
  """Return the text to print when there are the wrong number of args."""
  lines = [
    "Usage: ./run_bm.py <minimizer> <benchmarkdir>",
    "",
    "<minimizer> is one of:",
  ]
  lines += [f"  {name}" for name in MINIMIZER_COMMANDS]
  return "\n".join(lines)


def validate_benchmark_dir(benchmark_dir: str) -> Optional[str]:
  """Return an error message if `benchmark_dir` is unusable, else None."""
  path = Path(benchmark_dir)
  if not path.is_dir():
    return f"Not a directory: {benchmark_dir}"
  if not os.access(path / "gen.sh", os.X_OK):
    return f"Missing generator script: {path / 'gen.sh'}"
  if not os.access(path / "test.sh", os.X_OK):
    return f"Missing test script: {path / 'test.sh'}"
  return None


def run_child(
  command: list[str],
  cwd: Path,
  env: dict[str, str],
) -> int:
  """
  Print `command`, run it in `cwd` with environment `env`, wait for it
  to terminate, and return a shell-style exit status.

  Ctrl-C goes to the whole process group, so the child sees it directly.
  It is up to the child to decide how to respond, so here we just keep
  waiting.  SIGTERM, however, is usually sent only to this process, and
  is forwarded to the child.
  """

  # Flush so our output does not appear after that of the child.
  print(shlex.join(command), flush=True)

  try:
    proc = subprocess.Popen(command, cwd=cwd, env=env)
  except FileNotFoundError as e:
    print(f"Cannot run {command[0]}: {e}", file=sys.stderr)
    return EXIT_NOT_FOUND
  except OSError as e:
    print(f"Cannot run {command[0]}: {e}", file=sys.stderr)
    return EXIT_CANNOT_EXECUTE

  def forward_signal(signum: int, frame: Optional[FrameType]) -> None:
    proc.send_signal(signum)

  old_handler = signal.signal(signal.SIGTERM, forward_signal)
  try:
    while True:
      try:
        status = proc.wait()
        break
      except KeyboardInterrupt:
        pass
  finally:
    signal.signal(signal.SIGTERM, old_handler)

  # A negative value means the child was killed by that signal.
  return 128 - status if status < 0 else status


def prepare_run_dir(benchmark_dir: Path, run_dir: Path) -> None:
  """
  Make `run_dir` a fresh copy of `benchmark_dir`, removing any prior
  run.  Failure raises OSError.
  """
  if run_dir.exists():
    print(shlex.join(["rm", "-r", str(run_dir)]))
    shutil.rmtree(run_dir)

  print(shlex.join(["mkdir", "-p", str(run_dir.parent)]))
  run_dir.parent.mkdir(parents=True, exist_ok=True)

  print(shlex.join(["cp", "-R", str(benchmark_dir), str(run_dir)]))
  shutil.copytree(benchmark_dir, run_dir, symlinks=True)


def run_minimizer(
  command: list[str],
  run_dir: Path,
  env: dict[str, str],
) -> int:
  """
  Run the minimizer `command`, print how long that took, and return its
  exit status.
  """
  before = os.times()
  status = run_child(command, run_dir, env)
  after = os.times()

  # Flush so this stays in order relative to any stderr output.
  print(
    f"Minimizer time: "
    f"real {after.elapsed - before.elapsed:.2f}s "
    f"user {after.children_user - before.children_user:.2f}s "
    f"sys {after.children_system - before.children_system:.2f}s",
    flush=True)

  return status


def main(argv: list[str]) -> int:
  """
  Run the program with arguments `argv` (not including the program
  name), and return its exit status.
  """

  if len(argv) != 2:
    print(usage_text())
    return EXIT_USAGE

  minimizer, benchmark_arg = argv

  if minimizer not in MINIMIZER_COMMANDS:
    print(f"Unrecognized minimizer: {minimizer}", file=sys.stderr)
    return EXIT_USAGE

  error = validate_benchmark_dir(benchmark_arg)
  if error is not None:
    print(error, file=sys.stderr)
    return EXIT_USAGE

  # The benchmark's name is the last component of its directory.  Making
  # the path absolute handles trailing slashes and names like ".".
  benchmark_dir = Path(os.path.abspath(benchmark_arg))
  benchmark: str = benchmark_dir.name

  print(f"Will run {minimizer} on benchmark: {benchmark}")

  run_dir = Path(os.path.abspath(Path("out") / benchmark / minimizer))

  try:
    prepare_run_dir(benchmark_dir, run_dir)
  except OSError as e:
    print(f"Cannot prepare {run_dir}: {e}", file=sys.stderr)
    return EXIT_FAILURE

  # Location of the acceptance test script, exported so test.sh can find
  # it from anywhere.
  env = dict(os.environ)
  env["T_ACCEPT_PY"] = str(REPO_DIR / "t_accept.py")

  # Generate the input to minimize.
  status = run_child(["./gen.sh"], run_dir, env)
  if status != 0:
    return status

  # Export the name of the log file so test.sh can log to it from
  # anywhere.  (creduce runs the program in a temporary directory.)
  env["T_ACCEPT_LOG_TSV"] = str(run_dir / f"{benchmark}-{minimizer}.tsv")

  return run_minimizer(MINIMIZER_COMMANDS[minimizer], run_dir, env)


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))


# EOF
