# lang_cpp.py
"""
CPPLanguage: the `Language` implementation for C and C++.
"""

from __future__ import annotations

from typing import Optional

from minimizer import NTReplacementFunc
from token_tree import TTNode
from tokenize_cpp import CPPTokenizer
from tokenizer import Tokenizer


class CPPLanguage:
  """Implementation of the `Language` protocol for C and C++."""

  def make_tokenizer(self) -> Tokenizer:
    return CPPTokenizer()

  def get_non_trivial_replacement_func(self) -> NTReplacementFunc:
    return self.non_trivial_replacement

  @staticmethod
  def non_trivial_replacement(node: TTNode) -> Optional[bytes]:
    """
    The `NTReplacementFunc` for C++: a brace group, such as a function
    body, can be replaced with ";".
    """
    if node.delim_group:
      opener = node.children[0].token
      assert opener is not None
      if opener.delimiter_kind == -3:
        return b";"
    return None


# EOF
