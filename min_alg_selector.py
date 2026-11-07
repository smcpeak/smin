# min_alg_selector.py
"""
MinimizerAlgorithmSelector class.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from min_alg_kind import MinimizerAlgorithmKind


class MinimizerAlgorithmSelector(ABC):
  """
  Choose which minimizer algorithm to use, and also optionally supply it
  with algorithm-specific options.

  This class is called a "selector" rather than "options" because (1) it
  plays the role of choosing the algorithm, and (2) that avoids
  potential confusion with the MinimizerOptions class (which carries
  options that apply to any algorithm).

  Concrete implementations are in ma_*.py, alongside the algorithms they
  select.
  """

  @abstractmethod
  def alg_kind(self) -> MinimizerAlgorithmKind:
    """Get the broad "kind" of algorithm this selector specifies."""
    ...


# EOF
