#!/usr/bin/env python3
# run_bm.py
"""
Run a minimizer on one of the benchmarks.

Usage:

  ./run_bm.py <minimizer> <benchmarkdir>

The results go into out/<benchmark>/<minimizer>, relative to the current
directory, replacing any prior run there.

The exit status is that of the minimizer if it ran, or 2 for any error
that prevented that, or 128+N if a child was killed by signal N.
"""

from __future__ import annotations

import os
import shlex
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import FrameType
from typing import Optional


# Directories containing this script and the minimizer sources.
BM_DIR: Path = Path(__file__).resolve().parent
REPO_DIR: Path = BM_DIR.parent

# Exit status for any fatal error.
EXIT_CODE_ERROR = 2

# The test script and the input it checks, within a run directory.
TEST_SH = "./test.sh"
INPUT = "input"

@dataclass(frozen=True)
class MinimizerSpec:
  """How to run one minimizer."""

  # The command that runs it in a run directory.
  command: list[str]

  # Additional environment variables to set while running the benchmark,
  # typically to enable experimental behavior.
  env: dict[str, str] = field(default_factory=dict)


# Map from minimizer name to how to run it.
_SMIN_PY: str = str(REPO_DIR / "smin.py")
_SMIN_MA2_BG: list[str] = [
  _SMIN_PY, "--ma2", "--ma2-brace-groups", TEST_SH, "--", INPUT]
MINIMIZERS: dict[str, MinimizerSpec] = {
  "smin":     MinimizerSpec([_SMIN_PY, TEST_SH, "--", INPUT]),
  "smin-ma2": MinimizerSpec([_SMIN_PY, "--ma2", TEST_SH, "--", INPUT]),
  "smin-hdd": MinimizerSpec([_SMIN_PY, "--hdd", TEST_SH, "--", INPUT]),
  "delta":    MinimizerSpec(["multimultidelta", TEST_SH, INPUT]),

  # --n 1 causes these to run sequentially.
  "creduce":  MinimizerSpec(["creduce", "--n", "1", TEST_SH, INPUT]),
  "cvise":    MinimizerSpec(["cvise", "--n", "1", TEST_SH, INPUT]),

  "smin-ma2-bg": MinimizerSpec(_SMIN_MA2_BG),

  # Like smin-ma2-bg, but skipping the paragraph grouping phase.
  "smin-ma2-bg-sp": MinimizerSpec(_SMIN_MA2_BG, env={"SKIP_PARA": "1"}),
}


def usage_text() -> str:
  """Return the text to print when there are the wrong number of args."""
  lines = [
    "Usage: ./run_bm.py <minimizer> <benchmarkdir>",
    "",
    "<minimizer> is one of:",
  ]
  lines += [f"  {name}" for name in MINIMIZERS]
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

  # Print the command to run, with shell quoting as needed.
  #
  # Flush so our output does not appear after that of the child.
  print(shlex.join(command), flush=True)

  try:
    proc = subprocess.Popen(command, cwd=cwd, env=env)
  except OSError as e:
    print(f"Cannot run {command[0]}: {e}", file=sys.stderr)
    return EXIT_CODE_ERROR

  def forward_signal(signum: int, frame: Optional[FrameType]) -> None:
    proc.send_signal(signum)

  # Arrange to send SIGTERM to the child if we receive it so the child
  # (which is often long-running) will not just keep running after this
  # script dies.
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
    return EXIT_CODE_ERROR

  minimizer, benchmark_arg = argv

  spec = MINIMIZERS.get(minimizer)
  if spec is None:
    print(f"Unrecognized minimizer: {minimizer}", file=sys.stderr)
    return EXIT_CODE_ERROR

  error = validate_benchmark_dir(benchmark_arg)
  if error is not None:
    print(error, file=sys.stderr)
    return EXIT_CODE_ERROR

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
    return EXIT_CODE_ERROR

  # Location of the acceptance test script, exported so test.sh can find
  # it from anywhere.
  env = dict(os.environ)
  env["T_ACCEPT_PY"] = str(REPO_DIR / "t_accept.py")

  # Variables specific to this minimizer.
  for name, value in spec.env.items():
    print(f"export {shlex.quote(f'{name}={value}')}")
    env[name] = value

  # Generate the input to minimize.
  status = run_child(["./gen.sh"], run_dir, env)
  if status != 0:
    print(f"Generating the input failed with status {status}.",
          file=sys.stderr)

    # A status above 128 means the generator was killed by a signal.
    return status if status > 128 else EXIT_CODE_ERROR

  # Export the name of the log file so test.sh can log to it from
  # anywhere.  (creduce runs the program in a temporary directory.)
  env["T_ACCEPT_LOG_TSV"] = str(run_dir / f"{benchmark}-{minimizer}.tsv")

  return run_minimizer(spec.command, run_dir, env)


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))


# EOF
