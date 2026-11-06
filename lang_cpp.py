# lang_cpp.py
"""
CPPLanguage: the `Language` implementation for C and C++.
"""

from __future__ import annotations

from typing import Optional

from lang_cpp_delims import CPP_BRACE
from minimizer import BraceGroupFunc, NTReplacementFunc
from token_tree import TTNode
from tokenize_cpp import CPPTokenizer
from tokenizer import Tokenizer


class CPPLanguage:
  """Implementation of the `Language` protocol for C and C++."""

  def make_tokenizer(self) -> Tokenizer:
    return CPPTokenizer()

  def get_non_trivial_replacement_func(self) -> NTReplacementFunc:
    return self.non_trivial_replacement

  def get_brace_group_func(self) -> BraceGroupFunc:
    return self.is_brace_group

  @staticmethod
  def is_brace_group(node: TTNode) -> bool:
    """The `BraceGroupFunc` for C++: True for a "{...}" group."""
    if node.delim_group:
      opener = node.children[0].token
      assert opener is not None
      return opener.delimiter_kind == -CPP_BRACE
    return False

  @staticmethod
  def non_trivial_replacement(node: TTNode) -> Optional[bytes]:
    """
    The `NTReplacementFunc` for C++: a brace group, such as a function
    body, can be replaced with ";".
    """
    if CPPLanguage.is_brace_group(node):
      return b";"
    return None


# EOF
