#!/usr/bin/env python3
# Sleep for 4 seconds, possibly ignoring SIGINT.

# This is meant to be used as the MANUAL_TEST_PROG for a test of the
# check_accept module, especially to test Ctrl-C behavior.

import signal
import time

if True:
  # Ignore SIGINT so Ctrl-C does not stop this.
  signal.signal(signal.SIGINT, signal.SIG_IGN)

print("Sleeping for 4 seconds ...")
time.sleep(4)
print("Done sleeping.")

# EOF
