#!/bin/sh
# Generate the input.

clang -E hello-cpp.cc | grep -v '^ *#' > input

# EOF
