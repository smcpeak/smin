#!/bin/sh

export INPUT=input

# In case I want to run this outside run_bm.py.
: "${T_ACCEPT_PY:=../../t_accept.py}"
: "${T_ACCEPT_LOG_TSV:=log.tsv}"

exec python3 "$T_ACCEPT_PY" \
    --before-after keep1 keep2 \
    --tsv-log "$T_ACCEPT_LOG_TSV" \
    >/dev/null 2>&1

# EOF
