#!/bin/sh
# Run smin on one of the benchmarks.

if [ "x$1" = "x" ]; then
  echo "Usage: $0 <benchmarkdir>"
  exit 2
fi

benchmarkdir="$1"

# Strip trailing slashes.
benchmarkdir=$(echo "$benchmarkdir" | sed 's,/*$,,')

if [ ! -d "$benchmarkdir" ]; then
  echo "Not a directory: $benchmarkdir" 1>&2
  exit 2
fi
echo "Will run smin on benchmarkdir: $benchmarkdir"

runecho() {
  printf "%s\n" "$*"
  "$@" || exit
}

if [ -e "out/smin/$benchmarkdir" ]; then
  runecho rm -r "out/smin/$benchmarkdir"
fi

runecho cp -R "$benchmarkdir" "out/smin/$benchmarkdir"

runecho cd "out/smin/$benchmarkdir"

runecho ./gen.sh

runecho ../../../../smin.py ./test.sh -- input


# EOF
