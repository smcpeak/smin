# t_accept_test.py
"""
Unit tests for t_accept.
"""

from __future__ import annotations

import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from t_accept import main


# The fake clang is a shell script.
POSIX = os.name == "posix"


class TAcceptTest(unittest.TestCase):
  def setUp(self) -> None:
    self.temp_dir = tempfile.TemporaryDirectory()
    self.dir = Path(self.temp_dir.name)
    self.input_path = self.dir / "input.cc"

    # Output of the most recent `run`.
    self.out = ""
    self.err = ""

  def tearDown(self) -> None:
    self.temp_dir.cleanup()

  def run_main(
    self,
    argv: list[str],
    contents: bytes | None = b"",
    env: dict[str, str] | None = None,
  ) -> int:
    """
    Run `main(argv)` with INPUT naming a file containing `contents`
    (unless it is None, in which case the file does not exist), and
    additional environment `env`.  Return the exit code.
    """
    if contents is not None:
      self.input_path.write_bytes(contents)
    new_env = {"INPUT": str(self.input_path)}
    new_env.update(env or {})

    out = io.StringIO()
    err = io.StringIO()
    with mock.patch.dict(os.environ, new_env), \
         contextlib.redirect_stdout(out), \
         contextlib.redirect_stderr(err):
      code = main(argv)
    self.out = out.getvalue()
    self.err = err.getvalue()
    return code

  def check(self, argv: list[str], contents: bytes, expect: int) -> None:
    """Check that `argv` on `contents` yields exit code `expect`."""
    self.assertEqual(self.run_main(argv, contents), expect,
                     f"argv={argv!r} contents={contents!r}")

  # ---- Checks ----

  def test_no_checks(self) -> None:
    self.check([], b"anything\n", 0)
    self.assertEqual(self.out, "")

  def test_has_string(self) -> None:
    self.check(["--has-string", "keep"], b"a\nto keep it\n", 0)
    self.check(["--has-string", "keep"], b"a\nb\n", 1)
    self.assertEqual(self.out, "reject: no line contains 'keep'\n")

  def test_has_string_within_one_line(self) -> None:
    self.check(["--has-string", "a b"], b"a\nb\n", 1)

  def test_has_string_all_required(self) -> None:
    argv = ["--has-string", "x", "--has-string", "y"]
    self.check(argv, b"x\ny\n", 0)
    self.check(argv, b"x\n", 1)
    self.check(argv, b"y\n", 1)

  def test_has_string_non_ascii(self) -> None:
    self.check(["--has-string", "é"], "café\n".encode(), 0)

  def test_has_regex(self) -> None:
    self.check(["--has-regex", r"int +x"], b"long y;\nint  x;\n", 0)
    self.check(["--has-regex", r"int +x"], b"intx;\n", 1)
    self.assertIn("no line matches", self.out)

  def test_has_regex_applies_to_each_line(self) -> None:
    # "^" and "$" match at the ends of each line.
    self.check(["--has-regex", r"^y;$"], b"x;\ny;\nz;\n", 0)
    self.check(["--has-regex", r"x.*z"], b"x;\nz;\n", 1)

  def test_balanced_delim_counts(self) -> None:
    argv = ["--balanced-delim-counts"]
    self.check(argv, b"f(a[1]) { }\n", 0)
    # Only the counts matter, not the order.
    self.check(argv, b")(][}{", 0)
    self.check(argv, b"f(a[1] { }\n", 1)
    self.check(argv, b"f(a[1]) { }]\n", 1)
    self.check(argv, b"f(a[1]) {\n", 1)
    self.assertEqual(self.out, "reject: unbalanced {} counts\n")

  def test_before_after(self) -> None:
    argv = ["--before-after", "decl", "use"]
    self.check(argv, b"decl\nother\nuse\n", 0)
    self.check(argv, b"use\ndecl\n", 1)
    # Strictly later: the same line does not count.
    self.check(argv, b"decl use\n", 1)
    # Any line with `before` will do, not just the last.
    self.check(argv, b"decl\nuse\ndecl\n", 0)
    self.check(argv, b"use\n", 1)
    self.check(argv, b"decl\n", 1)

  def test_before_after_repeated(self) -> None:
    argv = ["--before-after", "a", "b", "--before-after", "b", "c"]
    self.check(argv, b"a\nb\nc\n", 0)
    self.check(argv, b"a\nc\nb\n", 1)

  def test_combined_checks(self) -> None:
    argv = ["--has-string", "main", "--balanced-delim-counts"]
    self.check(argv, b"int main() {}\n", 0)
    self.check(argv, b"int main() {\n", 1)
    self.check(argv, b"int f() {}\n", 1)

  # ---- --clang ----

  def make_fake_clang(self) -> dict[str, str]:
    """
    Create a fake "clang" that succeeds if it is given the expected
    arguments and its input does not contain "error".  Return the
    environment changes that put it first on the PATH.
    """
    bin_dir = self.dir / "bin"
    bin_dir.mkdir()
    clang = bin_dir / "clang"
    clang.write_text(
      "#!/bin/sh\n"
      '[ "$#" = 3 ] && [ "$1" = -fsyntax-only ] && [ "$2" = -xc++ ] &&\n'
      '  [ "$3" = "$INPUT" ] || exit 99\n'
      'if grep -q error "$3"; then exit 1; fi\n'
      "exit 0\n")
    clang.chmod(0o755)
    return {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}

  @unittest.skipUnless(POSIX, "uses a shell script")
  def test_clang_accept(self) -> None:
    env = self.make_fake_clang()
    self.assertEqual(self.run_main(["--clang"], b"int x;\n", env), 0)

  @unittest.skipUnless(POSIX, "uses a shell script")
  def test_clang_reject(self) -> None:
    env = self.make_fake_clang()
    self.assertEqual(self.run_main(["--clang"], b"error\n", env), 1)
    self.assertEqual(self.out, "reject: clang exited with code 1\n")

  @unittest.skipUnless(POSIX, "uses a shell script")
  def test_clang_not_run_if_earlier_check_fails(self) -> None:
    # The fake clang would accept, but the string check fails first.
    env = self.make_fake_clang()
    code = self.run_main(["--clang", "--has-string", "y"], b"x\n", env)
    self.assertEqual(code, 1)
    self.assertIn("no line contains", self.out)

  def test_clang_not_found(self) -> None:
    empty_dir = self.dir / "empty"
    empty_dir.mkdir()
    code = self.run_main(["--clang"], b"int x;\n",
                         {"PATH": str(empty_dir)})
    self.assertEqual(code, 2)
    self.assertIn("cannot run clang", self.err)

  # ---- --sleep ----

  def test_sleep(self) -> None:
    start = time.monotonic()
    self.check(["--sleep", "0.2"], b"", 0)
    self.assertGreaterEqual(time.monotonic() - start, 0.2)

  def test_sleep_invalid(self) -> None:
    self.check(["--sleep", "soon"], b"", 2)

  # ---- --capture and --log ----

  TIMESTAMP = r"\d+\.\d{9}"

  def test_capture(self) -> None:
    capture_dir = self.dir / "captures"
    self.check(["--capture", str(capture_dir)], b"first\n", 0)
    self.check(["--capture", str(capture_dir),
                "--has-string", "x"], b"second\n", 1)

    # Both inputs are captured, whatever the verdict.
    files = sorted(capture_dir.iterdir())
    self.assertEqual(len(files), 2)
    for f in files:
      self.assertRegex(f.name, f"^input-{self.TIMESTAMP}$")
    self.assertEqual(sorted(f.read_bytes() for f in files),
                     [b"first\n", b"second\n"])

  def test_capture_timestamp_is_invocation_time(self) -> None:
    before = time.time()
    self.check(["--capture", str(self.dir)], b"", 0)
    after = time.time()
    (captured,) = self.dir.glob("input-*")
    stamp = float(captured.name.removeprefix("input-"))
    self.assertLessEqual(before - 1, stamp)
    self.assertLessEqual(stamp, after + 1)

  def test_log(self) -> None:
    log = self.dir / "log.txt"
    self.check(["--log", str(log), "--has-string", "a"], b"a\n", 0)
    self.check(["--log", str(log), "--has-string", "a"], b"b\n", 1)

    lines = log.read_text().splitlines()
    self.assertEqual(len(lines), 2)
    name = re.escape(str(self.input_path))
    self.assertRegex(lines[0], f"^{name} {self.TIMESTAMP} accept$")
    self.assertRegex(lines[1], f"^{name} {self.TIMESTAMP} reject$")

  def test_log_with_capture(self) -> None:
    log = self.dir / "log.txt"
    capture_dir = self.dir / "captures"
    self.check(["--log", str(log), "--capture", str(capture_dir)],
               b"data\n", 0)

    (captured,) = capture_dir.iterdir()
    stamp = captured.name.removeprefix("input-")
    self.assertEqual(
      log.read_text(),
      f"{self.input_path} {stamp} accept {captured}\n")

  # ---- Errors ----

  def test_input_not_set(self) -> None:
    out = io.StringIO()
    err = io.StringIO()
    env = {k: v for k, v in os.environ.items() if k != "INPUT"}
    with mock.patch.dict(os.environ, env, clear=True), \
         contextlib.redirect_stdout(out), \
         contextlib.redirect_stderr(err):
      code = main([])
    self.assertEqual(code, 2)
    self.assertIn("INPUT", err.getvalue())

  def test_input_unreadable(self) -> None:
    self.assertEqual(self.run_main([], contents=None), 2)
    self.assertIn("cannot read", self.err)

  def test_unknown_option(self) -> None:
    self.check(["--bogus"], b"", 2)

  def test_missing_option_argument(self) -> None:
    self.check(["--before-after", "x"], b"", 2)

  def test_help(self) -> None:
    self.check(["--help"], b"", 0)
    self.assertIn("usage:", self.out)

  # ---- Running as a program ----

  def test_run_as_program(self) -> None:
    script = Path(__file__).parent / "t_accept.py"
    self.input_path.write_bytes(b"keep\n")
    env = dict(os.environ, INPUT=str(self.input_path))
    for s, expect in (("keep", 0), ("other", 1)):
      proc = subprocess.run(
        [sys.executable, str(script), "--has-string", s],
        env=env, capture_output=True, check=False)
      self.assertEqual(proc.returncode, expect)


if __name__ == "__main__":
  unittest.main()


# EOF
