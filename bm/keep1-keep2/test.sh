#!/bin/sh

export INPUT=input

exec python3 "$T_ACCEPT_PY" \
    --before-after keep1 keep2 \
    --tsv-log "$T_ACCEPT_LOG_TSV" \
    >/dev/null 2>&1

# EOF
