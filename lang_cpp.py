# lang_cpp.py
"""
CPPLanguage: the `Language` implementation for C and C++.
"""

from __future__ import annotations

from typing import Optional

from lang_cpp_delims import CPP_BRACE
from token_tree import TTNode
from tokenize_cpp import CPPTokenizer
from tokenizer import Tokenizer


class CPPLanguage:
  """Implementation of the `Language` protocol for C and C++."""

  def make_tokenizer(self) -> Tokenizer:
    return CPPTokenizer()

  def is_brace_group(self, node: TTNode) -> bool:
    """True for a "{...}" group."""
    if node.is_delim_group():
      opener = node.children[0].token
      assert opener is not None
      return opener.delimiter_kind == -CPP_BRACE
    return False

  def non_trivial_replacement(self, node: TTNode) -> Optional[bytes]:
    """
    A brace group, such as a function body, can be replaced with ";".
    """
    if self.is_brace_group(node):
      return b";"
    return None


# EOF
