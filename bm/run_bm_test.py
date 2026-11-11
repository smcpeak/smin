# run_bm_test.py
"""
Unit tests for run_bm.

Everything here runs with a temporary directory as the current directory
of the script, because run_bm replaces the prior run in out/, and real
benchmark results must not be disturbed by running the tests.
"""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from bm.run_bm import (
  BM_DIR,
  EXIT_CODE_ERROR,
  MINIMIZERS,
  REPO_DIR,
  MinimizerSpec,
  main,
  prepare_run_dir,
  run_child,
)


RUN_BM_PY: Path = BM_DIR / "run_bm.py"

# How long to wait for a child in the tests that signal it, in seconds.
SIGNAL_TEST_TIMEOUT = 30


def write_script(path: Path, body: str) -> None:
  """Write `body` as an executable shell script at `path`."""
  path.write_text(f"#!/bin/sh\n{body}\n")
  path.chmod(path.stat().st_mode | stat.S_IXUSR)


class TempDirTestCase(unittest.TestCase):
  """Base class for tests that use a temporary directory."""

  def setUp(self) -> None:
    tmp = tempfile.TemporaryDirectory()
    self.addCleanup(tmp.cleanup)
    self.tmp = Path(tmp.name)

  def make_benchmark(
    self,
    name: str = "bench",
    gen_body: str = ": > input",
  ) -> Path:
    """Create a benchmark directory, returning its path."""
    bench = self.tmp / name
    bench.mkdir()
    write_script(bench / "gen.sh", gen_body)
    write_script(bench / "test.sh", "exit 0")
    return bench


class ValidationTest(TempDirTestCase):
  """Tests of argument checking, which all stop before doing anything."""

  def run_main(self, argv: list[str]) -> tuple[int, str, str]:
    """Run `main`, returning its status, stdout, and stderr."""
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
      status = main(argv)
    return status, out.getvalue(), err.getvalue()

  def check_error(self, argv: list[str], message: str) -> None:
    status, out, err = self.run_main(argv)
    self.assertEqual(status, EXIT_CODE_ERROR)
    self.assertEqual(out, "")
    self.assertEqual(err, message + "\n")

  def test_usage(self) -> None:
    # Test passing the wrong number of arguments.
    for argv in ([], ["bench"]):
      status, out, err = self.run_main(argv)
      self.assertEqual(status, EXIT_CODE_ERROR)
      self.assertEqual(err, "")
      self.assertIn(
        "Usage: ./run_bm.py <benchmarkdir> <minimizer> "
        "[<variant> [<min-options>]]",
        out)

  def test_unrecognized_minimizer(self) -> None:
    bench = self.make_benchmark()
    self.check_error([str(bench), "bogus"], "Unrecognized minimizer: bogus")

  def test_invalid_variant(self) -> None:
    bench = self.make_benchmark()
    self.check_error([str(bench), "smin", ""], "Invalid variant: ''")
    self.check_error([str(bench), "smin", "a/b"], "Invalid variant: 'a/b'")

  def test_not_a_directory(self) -> None:
    missing = str(self.tmp / "missing")
    self.check_error([missing, "smin"], f"Not a directory: {missing}")

  def test_missing_scripts(self) -> None:
    bench = self.make_benchmark()
    (bench / "test.sh").unlink()
    self.check_error([str(bench), "smin"],
                     f"Missing test script: {bench}/test.sh")
    (bench / "gen.sh").unlink()
    self.check_error([str(bench), "smin"],
                     f"Missing generator script: {bench}/gen.sh")

  def test_scripts_must_be_executable(self) -> None:
    bench = self.make_benchmark()
    (bench / "gen.sh").chmod(0o644)
    self.check_error([str(bench), "smin"],
                     f"Missing generator script: {bench}/gen.sh")


class MinimizerSpecTest(unittest.TestCase):
  def test_get_command(self) -> None:
    spec = MinimizerSpec(["prog", "-a"], ["test.sh", "input"])
    self.assertEqual(spec.get_command([]),
                     ["prog", "-a", "test.sh", "input"])
    self.assertEqual(spec.get_command(["-b", "c d"]),
                     ["prog", "-a", "-b", "c d", "test.sh", "input"])


class RunChildTest(TempDirTestCase):
  def run_child(self, command: list[str]) -> tuple[int, str, str]:
    """Run `run_child`, returning its status, stdout, and stderr."""
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
      status = run_child(command, self.tmp, dict(os.environ, MYVAR="myval"))
    return status, out.getvalue(), err.getvalue()

  def test_echoes_with_quoting(self) -> None:
    status, out, _ = self.run_child(["true", "a b"])
    self.assertEqual(status, 0)
    self.assertEqual(out, "true 'a b'\n")

  def test_cwd_and_env(self) -> None:
    status, _, _ = self.run_child(["sh", "-c", 'echo "$MYVAR" > result'])
    self.assertEqual(status, 0)
    self.assertEqual((self.tmp / "result").read_text(), "myval\n")

  def test_exit_status(self) -> None:
    self.assertEqual(self.run_child(["sh", "-c", "exit 3"])[0], 3)

  def test_killed_by_signal(self) -> None:
    self.assertEqual(self.run_child(["sh", "-c", "kill -9 $$"])[0], 128 + 9)

  def test_not_found(self) -> None:
    status, _, err = self.run_child([str(self.tmp / "missing")])
    self.assertEqual(status, EXIT_CODE_ERROR)
    self.assertIn("Cannot run", err)

  def test_not_executable(self) -> None:
    prog = self.tmp / "prog"
    prog.write_text("")
    prog.chmod(0o644)
    status, _, err = self.run_child([str(prog)])
    self.assertEqual(status, EXIT_CODE_ERROR)
    self.assertIn("Cannot run", err)

  def test_restores_sigterm_handler(self) -> None:
    before = signal.getsignal(signal.SIGTERM)
    self.run_child(["true"])
    self.assertEqual(signal.getsignal(signal.SIGTERM), before)


class PrepareRunDirTest(TempDirTestCase):
  def prepare(self, bench: Path, run_dir: Path) -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
      prepare_run_dir(bench, run_dir)
    return out.getvalue()

  def test_creates_copy(self) -> None:
    bench = self.make_benchmark()
    (bench / "data").write_text("hello")
    run_dir = self.tmp / "out" / "bench" / "smin"
    out = self.prepare(bench, run_dir)

    self.assertEqual((run_dir / "data").read_text(), "hello")
    self.assertTrue(os.access(run_dir / "gen.sh", os.X_OK))
    self.assertTrue(os.access(run_dir / "test.sh", os.X_OK))
    self.assertEqual(out.splitlines(), [
      f"mkdir -p {run_dir.parent}",
      f"cp -R {bench} {run_dir}",
    ])

  def test_removes_prior_run(self) -> None:
    bench = self.make_benchmark()
    run_dir = self.tmp / "out" / "bench" / "smin"
    self.prepare(bench, run_dir)
    (run_dir / "stale").write_text("")

    out = self.prepare(bench, run_dir)
    self.assertFalse((run_dir / "stale").exists())
    self.assertEqual(out.splitlines()[0], f"rm -r {run_dir}")

  def test_leaves_other_minimizers_alone(self) -> None:
    bench = self.make_benchmark()
    other = self.tmp / "out" / "bench" / "delta"
    self.prepare(bench, other)
    (other / "result").write_text("")

    self.prepare(bench, self.tmp / "out" / "bench" / "smin")
    self.assertTrue((other / "result").exists())


class ScriptTest(TempDirTestCase):
  """
  Run the script as a child process, in `self.cwd`, using a stand-in for
  a third-party minimizer, so these need nothing to be installed.
  """

  def setUp(self) -> None:
    super().setUp()
    self.cwd = self.tmp / "cwd"
    self.cwd.mkdir()
    self.bin_dir = self.tmp / "bin"
    self.bin_dir.mkdir()
    self.env = dict(
      os.environ,
      PATH=f"{self.bin_dir}{os.pathsep}{os.environ['PATH']}")

    # Make sure the variables we check come from the script.
    self.env.pop("T_ACCEPT_PY", None)
    self.env.pop("T_ACCEPT_TSV_LOG", None)

  def fake_delta(self, body: str) -> None:
    """Install a stand-in for the "delta" minimizer's program."""
    write_script(self.bin_dir / "multimultidelta", body)

  def run_script(
    self,
    *args: str,
  ) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
      [sys.executable, str(RUN_BM_PY), *args],
      cwd=self.cwd, env=self.env,
      capture_output=True, text=True, check=False)

  def run_dir(
    self,
    benchmark: str = "bench",
    run_name: str = "delta",
  ) -> Path:
    return self.cwd / "out" / benchmark / run_name

  def fake_delta_logging_args(self) -> None:
    """Install a "delta" that logs its arguments, one per line."""
    self.fake_delta(
      'echo "tsv=$T_ACCEPT_TSV_LOG" > delta.log\n'
      'printf "arg=%s\\n" "$@" >> delta.log')

  def test_environment_and_arguments(self) -> None:
    bench = self.make_benchmark(gen_body=(
      'echo "gen_py=$T_ACCEPT_PY" > gen.log\n'
      'echo "gen_tsv=$T_ACCEPT_TSV_LOG" >> gen.log\n'
      'pwd >> gen.log\n'
      ': > input'))
    self.fake_delta(
      'echo "py=$T_ACCEPT_PY" > delta.log\n'
      'echo "tsv=$T_ACCEPT_TSV_LOG" >> delta.log\n'
      'echo "args=$*" >> delta.log\n'
      'pwd >> delta.log\n'
      'test -e input && echo "have input" >> delta.log')

    proc = self.run_script(str(bench), "delta")
    self.assertEqual(proc.returncode, 0, proc.stderr)

    # `pwd` reports the path with any symlinks resolved.
    run_dir = self.run_dir()
    real_run_dir = run_dir.resolve()
    t_accept = REPO_DIR / "t_accept.py"
    self.assertEqual((run_dir / "gen.log").read_text().splitlines(), [
      f"gen_py={t_accept}",
      "gen_tsv=",
      str(real_run_dir),
    ])
    self.assertEqual((run_dir / "delta.log").read_text().splitlines(), [
      f"py={t_accept}",
      f"tsv={run_dir}/bench-delta.tsv",
      "args=./test.sh input",
      str(real_run_dir),
      "have input",
    ])

    self.assertIn("Will run delta on benchmark: bench\n", proc.stdout)
    self.assertRegex(proc.stdout, r"Minimizer time: real \S+s user \S+s sys")

  def test_variant(self) -> None:
    bench = self.make_benchmark()
    self.fake_delta_logging_args()

    proc = self.run_script(str(bench), "delta", "v1")
    self.assertEqual(proc.returncode, 0, proc.stderr)

    # The variant names the results directory and TSV file, but adds no
    # arguments.
    run_dir = self.run_dir(run_name="delta-v1")
    self.assertEqual((run_dir / "delta.log").read_text().splitlines(), [
      f"tsv={run_dir}/bench-delta-v1.tsv",
      "arg=./test.sh",
      "arg=input",
    ])
    self.assertIn("Will run delta-v1 on benchmark: bench\n", proc.stdout)

    # The run without a variant is a separate directory.
    self.assertFalse(self.run_dir().exists())

  def test_variant_and_options(self) -> None:
    bench = self.make_benchmark()
    self.fake_delta_logging_args()

    proc = self.run_script(str(bench), "delta", "v2", "-x", "a b", "--y")
    self.assertEqual(proc.returncode, 0, proc.stderr)

    # The options go between the command prefix and suffix, intact.
    run_dir = self.run_dir(run_name="delta-v2")
    self.assertEqual((run_dir / "delta.log").read_text().splitlines(), [
      f"tsv={run_dir}/bench-delta-v2.tsv",
      "arg=-x",
      "arg=a b",
      "arg=--y",
      "arg=./test.sh",
      "arg=input",
    ])

    # The command is echoed with quoting.
    self.assertIn("multimultidelta -x 'a b' --y ./test.sh input\n",
                  proc.stdout)

  def test_trailing_slashes(self) -> None:
    bench = self.make_benchmark()
    self.fake_delta("exit 0")
    proc = self.run_script(f"{bench}//", "delta")
    self.assertEqual(proc.returncode, 0, proc.stderr)
    self.assertTrue((self.run_dir() / "input").exists())

  def test_relative_benchmark_path(self) -> None:
    self.make_benchmark()
    self.fake_delta("exit 0")
    proc = self.run_script("../bench", "delta")
    self.assertEqual(proc.returncode, 0, proc.stderr)
    self.assertTrue((self.run_dir() / "input").exists())

  def test_replaces_prior_run(self) -> None:
    bench = self.make_benchmark()
    self.fake_delta("exit 0")
    self.assertEqual(self.run_script(str(bench), "delta").returncode, 0)
    (self.run_dir() / "stale").write_text("")
    self.assertEqual(self.run_script(str(bench), "delta").returncode, 0)
    self.assertFalse((self.run_dir() / "stale").exists())

  def test_minimizer_status_forwarded(self) -> None:
    bench = self.make_benchmark()
    self.fake_delta("exit 7")
    self.assertEqual(self.run_script(str(bench), "delta").returncode, 7)

  def test_minimizer_not_installed(self) -> None:
    bench = self.make_benchmark()
    self.env["PATH"] = str(self.bin_dir)
    proc = self.run_script(str(bench), "delta")
    self.assertEqual(proc.returncode, EXIT_CODE_ERROR)
    self.assertIn("Cannot run multimultidelta", proc.stderr)

  def test_gen_failure_stops(self) -> None:
    bench = self.make_benchmark(gen_body="exit 5")
    self.fake_delta(": > ran")
    proc = self.run_script(str(bench), "delta")
    self.assertEqual(proc.returncode, EXIT_CODE_ERROR)
    self.assertIn("failed with status 5", proc.stderr)
    self.assertFalse((self.run_dir() / "ran").exists())

  def test_gen_killed_by_signal(self) -> None:
    bench = self.make_benchmark(gen_body="kill -9 $$")
    self.fake_delta(": > ran")
    proc = self.run_script(str(bench), "delta")
    self.assertEqual(proc.returncode, 128 + 9)
    self.assertFalse((self.run_dir() / "ran").exists())

  def test_prepare_failure(self) -> None:
    # A file is in the way of the output directory.
    bench = self.make_benchmark()
    (self.cwd / "out").write_text("")
    proc = self.run_script(str(bench), "delta")
    self.assertEqual(proc.returncode, EXIT_CODE_ERROR)
    self.assertIn("Cannot prepare", proc.stderr)

  def start_sleeping_minimizer(self) -> subprocess.Popen[str]:
    """
    Start the script with a minimizer that sleeps, in its own process
    group, and wait for the minimizer to start.
    """
    bench = self.make_benchmark()
    self.fake_delta(": > started\nexec sleep 300")
    proc = subprocess.Popen(
      [sys.executable, str(RUN_BM_PY), str(bench), "delta"],
      cwd=self.cwd, env=self.env, text=True, start_new_session=True,
      stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def cleanup() -> None:
      with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGKILL)
      proc.communicate()

    self.addCleanup(cleanup)

    started = self.run_dir() / "started"
    deadline = time.monotonic() + SIGNAL_TEST_TIMEOUT
    while not started.exists():
      self.assertLess(time.monotonic(), deadline)
      time.sleep(0.01)
    return proc

  def test_sigterm_forwarded(self) -> None:
    # The signal goes only to the script, and it takes down the minimizer.
    proc = self.start_sleeping_minimizer()
    proc.send_signal(signal.SIGTERM)
    _, err = proc.communicate(timeout=SIGNAL_TEST_TIMEOUT)
    self.assertEqual(proc.returncode, 128 + signal.SIGTERM)
    self.assertEqual(err, "")

  def test_ctrl_c(self) -> None:
    # Like Ctrl-C, the signal goes to the process group.  The script
    # reports the minimizer's status rather than dying with a traceback.
    proc = self.start_sleeping_minimizer()
    os.killpg(proc.pid, signal.SIGINT)
    out, err = proc.communicate(timeout=SIGNAL_TEST_TIMEOUT)
    self.assertEqual(proc.returncode, 128 + signal.SIGINT)
    self.assertEqual(err, "")
    self.assertIn("Minimizer time:", out)



class MinimizerEnvTest(TempDirTestCase):
  """Tests of the extra environment variables a minimizer can specify."""

  def test_env_is_set(self) -> None:
    # Run `main` in-process, with a stand-in minimizer added to the
    # table, and the temporary directory as the current directory.
    bench = self.make_benchmark(gen_body=(
      'echo "gen=$MY_VAR" > gen.log\n'
      ': > input'))
    fake = self.tmp / "fake-minimizer"
    write_script(fake, 'echo "min=$MY_VAR" > min.log')
    spec = MinimizerSpec([str(fake)], [], env={"MY_VAR": "a b"})

    out = io.StringIO()
    with mock.patch.dict(MINIMIZERS, {"fake": spec}), \
         contextlib.chdir(self.tmp), \
         contextlib.redirect_stdout(out):
      status = main([str(bench), "fake"])

    self.assertEqual(status, 0)
    self.assertIn("export 'MY_VAR=a b'\n", out.getvalue())
    run_dir = self.tmp / "out" / "bench" / "fake"
    self.assertEqual((run_dir / "gen.log").read_text(), "gen=a b\n")
    self.assertEqual((run_dir / "min.log").read_text(), "min=a b\n")


@unittest.skipUnless(os.environ.get("SLOW") == "1", "requires SLOW=1")
@unittest.skipUnless(shutil.which("clang"), "requires clang")
class EndToEndTest(TempDirTestCase):
  def test_smin_on_hello_cpp(self) -> None:
    # Use the real benchmark, but with the output under a temporary
    # directory, rather than bm/out.
    proc = subprocess.run(
      [sys.executable, str(RUN_BM_PY), str(BM_DIR / "hello-cpp"), "smin"],
      cwd=self.tmp, capture_output=True, text=True, check=False)
    self.assertEqual(proc.returncode, 0, proc.stderr)
    self.assertEqual(proc.stderr, "")

    run_dir = self.tmp / "out" / "hello-cpp" / "smin"

    # This is the same input and the same acceptance criteria as the
    # hello-cpp.cc.ok target in the Makefile.
    original = (BM_DIR / "hello-cpp" / "hello-cpp.cc").read_bytes()
    self.assertEqual((run_dir / "input.bak").read_bytes(), original)
    expected = (REPO_DIR / "test" / "hello-cpp.cc.exp").read_bytes()
    self.assertEqual((run_dir / "input").read_bytes(), expected)

    self.assertIn(
      f"from 67 tokens ({len(original)} bytes) "
      f"to 17 tokens ({len(expected)} bytes).",
      proc.stdout)
    self.assertIn("Minimizer time:", proc.stdout)

    # The acceptance test logged to the TSV.  The last accepted row has
    # the final size.
    rows = [
      line.split("\t")
      for line in (run_dir / "hello-cpp-smin.tsv").read_text().splitlines()
    ]
    self.assertEqual(rows[0][1:3], ["TRUE", str(len(original))])
    accepted = [r for r in rows if r[1] == "TRUE"]
    self.assertEqual(accepted[-1][2], str(len(expected)))

    # The benchmark itself is left alone.
    self.assertFalse((BM_DIR / "hello-cpp" / "input").exists())


if __name__ == "__main__":
  unittest.main()


# EOF
