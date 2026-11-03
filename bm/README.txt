This directory holds some benchmarks, and the scripts to run them on
some chosen minimizers.

The main script is run-bm.sh.  Run it without arguments to see usage.

Individual benchmarks are in subdirectories of this one.

When run-bm.sh runs a benchmark, it puts a TSV into:

  out/$benchmark/$minimizer/$benchmark-$minimizer.tsv

The TSV files can be fed to ../gnuplot_tsv.py for comparison, even while
the benchmarks are still running (although it does not update the plot
in real time; it just sees a snapshot).


EOF
