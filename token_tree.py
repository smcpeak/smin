# token_tree.py
"""
Token tree data structure produced by the structure deduction algorithm.

See structure-deduction-algorithm.txt, "Output" section.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from smin_token import SMToken
from string_util import quote_bytes
from whitespace import only_whitespace


class TTNodeKind(Enum):
  """
  Kind of node, especially for distinguishing different sorts of group
  nodes.  The phases are described in structure-deduction-algorithm.txt.
  """

  # Node is a leaf carrying a token.
  TOKEN = 0

  # Node is the root of the tree.
  ROOT = 1

  # Phase 2 delimiter group, with opening and closing delimiters at both
  # ends.  These are special in several respects, among them being that
  # later phases never place the delimiters into smaller groups.
  DELIMITER = 2

  # Phase 3 line group.
  LINE = 3

  # Phase 4 indentation group.
  INDENTATION = 4

  # Phase 4.5 head-body group.
  HEAD_BODY = 5

  # Phase 5 paragraph gruop.
  PARAGRAPH = 6


@dataclass
class TTNode:
  """
  A token tree node: either a token (leaf) or a group (interior).

  Exactly one of `token` and `children` is meaningful: a token node has
  `token` set and no children, while a group node has `token` None and
  a sequence of child nodes.
  """

  # Which kind of node this is.
  kind: TTNodeKind

  # The token, if `kind == TTNodeKind.TOKEN`.
  token: SMToken | None = None

  # Child nodes, if this is a group node (`kind != TTNodeKind.TOKEN`).
  children: list[TTNode] = field(default_factory=list)


  @staticmethod
  def make_token(token: SMToken) -> TTNode:
    return TTNode(kind=TTNodeKind.TOKEN, token=token)

  @staticmethod
  def make_group(kind: TTNodeKind, children: list[TTNode]) -> TTNode:
    return TTNode(kind=kind, children=children)

  def is_token(self) -> bool:
    return self.kind == TTNodeKind.TOKEN

  def is_group(self) -> bool:
    return self.kind != TTNodeKind.TOKEN

  def is_delim_group(self) -> bool:
    return self.kind == TTNodeKind.DELIMITER

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

  def depth(self) -> int:
    """
    Return the number of edges on the longest path from this node down
    to a leaf.
    """
    if not self.children:
      return 0
    return 1 + max(child.depth() for child in self.children)

  def self_check(self) -> None:
    """Assert data structure invariants."""
    if self.is_token():
      assert self.token is not None, "token node missing token value"
      assert not self.children, "token node has children"

    else:
      if self.is_delim_group():
        assert len(self.children) >= 2, "delim group lacks delimiters"
        assert self.children[0].is_token(), "opener is not a token"
        assert self.children[-1].is_token(), "closer is not a token"

      for child in self.children:
        child.self_check()

  def to_debug_string(self, indent: int = 0) -> str:
    """
    Render in the bracket notation used by the algorithm examples.

    Groups are enclosed in brackets, with one child per line, and
    tokens are C-style quoted strings.
    """
    pad = " " * indent
    if self.token is not None:
      return pad + quote_bytes(self.token.text) + "\n"
    parts = [pad + self.kind.name + "[\n"]
    for child in self.children:
      parts.append(child.to_debug_string(indent + 2))
    parts.append(pad + "]\n")
    return "".join(parts)


@dataclass
class TokenTree:
  """
  The entire tree, wrapped as its own object.
  """

  # The root node of the tree.
  root: TTNode

  # If the final token produced by the tokenizer consists only of
  # characters in `whitespace.WHITESPACE_BYTES_SET`, then it is placed
  # here, and not part of the tree rooted at `root`.  Otherwise, this is
  # None.
  eof_ws: Optional[SMToken]


  def tokens(self) -> Iterator[SMToken]:
    """
    Yield all of the tokens in left-to-right order, including `eof_ws`
    if it is not None.
    """
    yield from self.root.tokens()
    if self.eof_ws is not None:
      yield self.eof_ws

  def text(self) -> bytes:
    """
    Return the concatenated text of all tokens, including `eof_ws`.
    This is the original input.
    """
    return b"".join(t.text for t in self.tokens())

  def depth(self) -> int:
    """Return the depth of `root`."""
    return self.root.depth()

  def self_check(self) -> None:
    """Assert data structure invariants."""
    self.root.self_check()

    if self.eof_ws is not None:
      assert self.eof_ws.text, "eof_ws is empty"
      assert only_whitespace(self.eof_ws.text), (
        "eof_ws has non-whitespace")

    # Any final whitespace token must be in `eof_ws`, not the tree.
    if self.root.children:
      assert not only_whitespace(self.root.last_token().text), (
        "tree ends with a whitespace token")

  def to_debug_string(self, indent: int = 0) -> str:
    r"""
    Render like:

      TokenTree{
        root: ROOT[
          ...
        ]
        eof_ws: "\n"
      }

    where the `root` part is `root.to_debug_string()`, and `eof_ws` is
    quoted like a token, or is None.
    """
    pad = " " * indent
    inner = " " * (indent + 2)
    root_str = self.root.to_debug_string(indent + 2)[len(inner):]
    eof_str = ("None" if self.eof_ws is None
               else quote_bytes(self.eof_ws.text))
    return (
      f"{pad}TokenTree{{\n"
      f"{inner}root: {root_str}"
      f"{inner}eof_ws: {eof_str}\n"
      f"{pad}}}\n")


# EOF
