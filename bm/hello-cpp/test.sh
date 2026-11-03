#!/bin/sh
# Test script for minimizer.

export INPUT=input

exec python3 "$T_ACCEPT_PY" \
    --clang \
    --before-after helper helper \
    --has-string std::cout \
    --tsv-log "$T_ACCEPT_LOG_TSV" \
    >/dev/null 2>&1

# EOF
