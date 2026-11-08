#!/bin/sh
# This input is somewhat interesting because it is a more or less
# minimal input for which `smin --max-passes=N` can only make progress
# if --skip-paragraphs is supplied.

cat >input <<END
int keep1;
a;

int keep2, b;
END

# EOF
