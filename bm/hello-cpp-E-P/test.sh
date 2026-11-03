#!/bin/sh
# Test script for minimizer.

export INPUT=input

exec python3 ../../../../t_accept.py \
    --clang \
    --before-after helper helper \
    --has-string std::cout \
    --tsv-log hello-cpp-E-P-smin.tsv

# EOF
