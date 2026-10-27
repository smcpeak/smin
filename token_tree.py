# token_tree.py
"""
Token tree data structure produced by the structure deduction algorithm.

See structure-deduction-algorithm.txt, "Output" section.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from smin_token import SMToken
from string_util import quote_bytes


@dataclass
class TTNode:
  """
  A token tree node: either a token (leaf) or a group (interior).

  Exactly one of `token` and `children` is meaningful: a token node has
  `token` set and no children, while a group node has `token` None and
  a sequence of child nodes.
  """

  # The token, if this is a token node.
  token: SMToken | None = None

  # Child nodes, if this is a group node.
  children: list[TTNode] = field(default_factory=list)

  # True if this group is bounded by delimiter tokens (its first and
  # last children), which are excluded from being placed into smaller
  # groups by later phases.
  delim_group: bool = False


  @staticmethod
  def make_token(token: SMToken) -> TTNode:
    return TTNode(token=token)

  @staticmethod
  def make_group(children: list[TTNode], delim_group: bool = False) -> TTNode:
    return TTNode(children=children, delim_group=delim_group)

  def is_token(self) -> bool:
    return self.token is not None

  def is_group(self) -> bool:
    return self.token is None

  def tokens(self) -> Iterator[SMToken]:
    """Yield the tokens under this node in left-to-right order."""
    if self.token is not None:
      yield self.token
    else:
      for child in self.children:
        yield from child.tokens()

  def first_token(self) -> SMToken:
    """Return the leftmost token under this node."""
    node = self
    while node.token is None:
      node = node.children[0]
    return node.token

  def last_token(self) -> SMToken:
    """Return the rightmost token under this node."""
    node = self
    while node.token is None:
      node = node.children[-1]
    return node.token

  def text(self) -> bytes:
    """Return the concatenated text of all tokens under this node."""
    return b"".join(t.text for t in self.tokens())

  def self_check(self) -> None:
    """Assert data structure invariants."""
    if self.token is not None:
      assert not self.children, "token node has children"
      assert not self.delim_group, "token node marked delim_group"
    else:
      if self.delim_group:
        assert len(self.children) >= 2, "delim group lacks delimiters"
        assert self.children[0].is_token(), "opener is not a token"
        assert self.children[-1].is_token(), "closer is not a token"
      for child in self.children:
        child.self_check()

  def to_debug_string(self, indent: int = 0) -> str:
    """Render in the bracket notation used by the algorithm examples.

    Groups are enclosed in brackets, with one child per line, and
    tokens are C-style quoted strings.
    """
    pad = " " * indent
    if self.token is not None:
      return pad + quote_bytes(self.token.text) + "\n"
    parts = [pad + "[\n"]
    for child in self.children:
      parts.append(child.to_debug_string(indent + 2))
    parts.append(pad + "]\n")
    return "".join(parts)


# EOF
