#!/bin/sh
# Cleanup preprocessed stdin, write cleaned to stdout.

# I'm experimenting with different steps to perform or not before
# minimization, so this script is a convenient place to put them.

# The first part strips '#' directives without using -P, which collapses
# a bunch of whitespace too.  Then the perl command collapses 3-or-more
# newlines to just 2, so a blank line remains but the long stretches of
# blank lines are removed.
grep -v '^ *#' | perl -0777 -pe 's/\n{3,}/\n\n/g'

# EOF
