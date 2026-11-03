#!/bin/sh
# Run a minimizer on one of the benchmarks.

# Print usage if no arguments.
if [ "x$1" = "x" ]; then
  echo "Usage: ./run-bm.sh <minimizer> <benchmarkdir>"
  echo ""
  echo "<minimizer> is one of:"
  echo "  smin"
  echo "  delta"
  echo "  creduce"
  exit 2
fi

if [ ! -x ./run-bm.sh ]; then
  echo "This script has to be run in the same directory that the " 1>&2
  echo "script lives in due to how T_ACCEPT_PY works." 1>&2
  exit 2
fi

# Validate the minimizer.
minimizer="$1"
case "$minimizer" in
  smin|delta|creduce|cvise)
    ;;

  *)
    echo "Unrecognized minimizer: $minimizer" 1>&2
    exit 2
    ;;
esac

benchmarkdir="$2"

# Strip trailing slashes.
benchmarkdir=$(echo "$benchmarkdir" | sed 's,/*$,,')

# Validate the benchmark directory.
if [ ! -d "$benchmarkdir" ]; then
  echo "Not a directory: $benchmarkdir" 1>&2
  exit 2
fi
if [ ! -x "$benchmarkdir/gen.sh" ]; then
  echo "Missing generator script: $benchmarkdir/gen.sh" 1>&2
  exit 2
fi
if [ ! -x "$benchmarkdir/test.sh" ]; then
  echo "Missing test script: $benchmarkdir/test.sh" 1>&2
  exit 2
fi
echo "Will run $minimizer on benchmarkdir: $benchmarkdir"

# Echo a command, then run it, and bail if it fails.
echo_run() {
  printf "%s\n" "$*"
  "$@" || exit
}

# Location of the acceptance test script, exported so test.sh can find
# it from anywhere.
export T_ACCEPT_PY="$(pwd)/../t_accept.py"

# Remove a prior run.
if [ -e "out/$benchmarkdir/$minimizer" ]; then
  echo_run rm -r "out/$benchmarkdir/$minimizer"
fi

# Copy the benchmark files into the test run directory.
echo_run mkdir -p "out/$benchmarkdir"
echo_run cp -R "$benchmarkdir" "out/$benchmarkdir/$minimizer"

echo_run cd "out/$benchmarkdir/$minimizer"

# Generate the input to minimize.
echo_run ./gen.sh

# Export the name of the log file so test.sh can log to it from
# anywhere.  (creduce runs the program in a temporary directory.)
export T_ACCEPT_LOG_TSV="$(pwd)/$benchmarkdir-$minimizer.tsv"

# Echo, then exec.  This is how the minimizer is run so that I can
# safely edit this script while it runs.
echo_exec() {
  printf "%s\n" "$*"
  exec "$@" || exit
}

# Run the minimizer.
case "$minimizer" in
  smin)
    echo_exec time ../../../../smin.py ./test.sh -- input
    ;;

  delta)
    echo_exec time multimultidelta ./test.sh input
    ;;

  creduce)
    # --n 1 causes it to run sequentially.
    echo_exec time creduce --n 1 ./test.sh input
    ;;

  cvise)
    # --n 1 causes it to run sequentially.
    echo_exec time cvise --n 1 ./test.sh input
    ;;

esac


# EOF
