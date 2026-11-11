#!/usr/bin/env python3
# run_bm.py
"""
Run a minimizer on one of the benchmarks.

Usage:

  ./run_bm.py <benchmarkdir> <minimizer> [<variant> [<min-options>]]

The results go into out/<benchmark>/<minimizer>[-<variant>], relative to
the current directory, replacing any prior run there.

If <variant> is provided, that string is simply appended (after a
hyphen) to <minimizer> to form the name of the results directory.

Anything that follows <variant> on the command line is treated as a
sequence of options to be passed to the minimizer.  When options are
present, the <variant> string should summarize them so that runs with
different options don't collide (but this script does not enforce that).

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

  # The first part of the command that runs it in a run directory.
  command_prefix: list[str]

  # The second part of the command.  Between the two are inserted
  # additional options specified on the `run_bm.py` command line.
  command_suffix: list[str]

  # Additional environment variables to set while running the benchmark,
  # typically to enable experimental behavior.
  env: dict[str, str] = field(default_factory=dict)


  def get_command(self, min_options: list[str]) -> list[str]:
    """
    Return the command to run, with `min_options` (<min-options> from
    the command line) inserted between the prefix and suffix.
    """
    return self.command_prefix + min_options + self.command_suffix


# Map from minimizer name to how to run it.
_SMIN_PY: str = str(REPO_DIR / "smin.py")
MINIMIZERS: dict[str, MinimizerSpec] = {
  "smin": MinimizerSpec(
    [_SMIN_PY],
    [TEST_SH, "--", INPUT]),

  # This minimizer is equivalent to "smin ma2 --ma2", i.e., using "ma2"
  # as the <variant> and "--ma2" as <min-options>.  For now, these
  # aliases are retained for convenience.
  "smin-ma2": MinimizerSpec(
    [_SMIN_PY, "--ma2"],
    [TEST_SH, "--", INPUT]),

  "smin-hdd": MinimizerSpec(
    [_SMIN_PY, "--hdd"],
    [TEST_SH, "--", INPUT]),

  "smin-ma3": MinimizerSpec(
    [_SMIN_PY, "--ma3"],
    [TEST_SH, "--", INPUT]),

  "smin-ma2-bg": MinimizerSpec(
    [_SMIN_PY, "--ma2", "--ma2-brace-groups"],
    [TEST_SH, "--", INPUT]),

  "smin-ma2-bg-sp": MinimizerSpec(
    [_SMIN_PY,
     "--ma2", "--ma2-brace-groups",
     "--skip-paragraphs"],
    [TEST_SH, "--", INPUT]),

  # This is my own script (in github.com/smcpeak/scripts) that runs
  # `multidelta -level=N` for N in the sequence [0 1 0 1 2 0 1 2 3 0 1 2
  # 3 4], thus performing a crude iterative deepening based on the
  # topformflat call inside multidelta.  That schedule is one I
  # developed myself via ad-hoc experimentation over the years, and (for
  # the inputs I've worked with) gets the best delta performance.
  "delta":    MinimizerSpec(
    ["multimultidelta"],
    [TEST_SH, INPUT]),

  # --n 1 causes creduce and cvise to run sequentially.
  "creduce":  MinimizerSpec(
    ["creduce", "--n", "1"],
    [TEST_SH, INPUT]),

  "cvise":    MinimizerSpec(
    ["cvise", "--n", "1"],
    [TEST_SH, INPUT]),
}


def usage_text() -> str:
  """Return the text to print when there are the wrong number of args."""
  lines = [
    ("Usage: ./run_bm.py <benchmarkdir> <minimizer> "
     "[<variant> [<min-options>]]"),
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

  if len(argv) < 2:
    print(usage_text())
    return EXIT_CODE_ERROR

  benchmark_arg, minimizer = argv[0], argv[1]
  variant: Optional[str] = argv[2] if len(argv) >= 3 else None
  min_options: list[str] = argv[3:]

  spec = MINIMIZERS.get(minimizer)
  if spec is None:
    print(f"Unrecognized minimizer: {minimizer}", file=sys.stderr)
    return EXIT_CODE_ERROR

  # Name of the results directory, which identifies this run.
  run_name: str = minimizer
  if variant is not None:
    # Reject variants that would not name a sibling of the other runs'
    # directories.
    if variant == "" or "/" in variant:
      print(f"Invalid variant: {variant!r}", file=sys.stderr)
      return EXIT_CODE_ERROR
    run_name += "-" + variant

  error = validate_benchmark_dir(benchmark_arg)
  if error is not None:
    print(error, file=sys.stderr)
    return EXIT_CODE_ERROR

  # The benchmark's name is the last component of its directory.  Making
  # the path absolute handles trailing slashes and names like ".".
  benchmark_dir = Path(os.path.abspath(benchmark_arg))
  benchmark: str = benchmark_dir.name

  print(f"Will run {run_name} on benchmark: {benchmark}")

  run_dir = Path(os.path.abspath(Path("out") / benchmark / run_name))

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
  env["T_ACCEPT_TSV_LOG"] = str(run_dir / f"{benchmark}-{run_name}.tsv")

  # Similarly, provide a name for --input-log.
  env["T_ACCEPT_INPUT_LOG"] = str(run_dir / f"input.log")

  return run_minimizer(spec.get_command(min_options), run_dir, env)


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))


# EOF
