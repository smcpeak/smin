# minimizer_options.py
"""
MinimizerOptions class.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional

from acceptance_tester import AcceptanceTester
from language import Language
from min_alg_kind import MinimizerAlgorithmKind
from min_alg_selector import MinimizerAlgorithmSelector


# Signature of a function called after each candidate is tested (and,
# if accepted, made current).  If it returns True, minimization stops.
# In normal operation, this checks whether a time limit has been
# reached.
StopQueryFunc = Callable[[], bool]


@dataclass(frozen=True, kw_only=True)
class MinimizerOptions:
  """
  Various options that control which minimizer algorithm to use, and the
  details of how that minimizer operates.
  """

  # Which algorithm and algorithm-specific options to use.
  selector: MinimizerAlgorithmSelector

  # Optional limit on the number of "passes", i.e., iterations of the
  # outer loop of the minimizer.
  max_passes: Optional[int]

  # Candidate tester, and recipient of the progress reports.
  acceptance: AcceptanceTester

  # Language-specific knowledge, such as non-trivial (non-empty) node
  # replacements.
  language: Language

  # Optional additional stop condition.
  should_stop: Optional[StopQueryFunc]


  def alg_kind(self) -> MinimizerAlgorithmKind:
    return self.selector.alg_kind()


# EOF
