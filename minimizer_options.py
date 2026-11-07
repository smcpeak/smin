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
from ma_kind import MinimizationAlgorithmKind


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

  # Which algorithm to use.
  alg_kind: MinimizationAlgorithmKind

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

  # If True, MA2 only considers the children of the root and of "brace
  # groups" (as identified by `language`) as candidates for removal.
  # See minimization-algorithm.txt, "MA2 --ma2-brace-groups".
  #
  # If this is True, then `alg_kind` must be MA2.
  #
  # TODO: Give this a default value.
  ma2_brace_groups: bool


  def __post_init__(self) -> None:
    if self.alg_kind != MinimizationAlgorithmKind.MA2:
      assert not self.ma2_brace_groups, (
        "Brace groups option requires MA2.")


# EOF
