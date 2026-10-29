# acceptance_test_result.py
"""AcceptanceTestResult enumeration."""

from enum import Enum


class AcceptanceTestResult(Enum):
  """Possible results of an acceptance test invocation."""
  ACCEPT = 1
  REJECT = 2
  INTERRUPTED = 3       # Ctrl-C


# EOF
