# build_tree.py
"""
Structure deduction: build a token tree from a token sequence.

See structure-deduction-algorithm.txt.
"""

from __future__ import annotations

from dataclasses import dataclass

from smin_token import SMToken
from token_tree import TTNode
from tokenizer import Tokenizer


_NEWLINE = ord("\n")

# Whitespace bytes, and the subset that counts toward indentation.
_WHITESPACE: frozenset[int] = frozenset(b" \t\r\f\v\n")
_INDENT_CHARS: frozenset[int] = frozenset(b" \t")


@dataclass(frozen=True)
class LineInfo:
  """Line-related properties of a token, as defined in Phase 1."""

  # Number of leading spaces and tabs on the line containing the
  # token's first non-whitespace character.
  indentation: int

  # True if there are no non-whitespace characters before the token on
  # that same line.
  first_on_line: bool


def compute_line_info(tokens: list[SMToken]) -> list[LineInfo]:
  """Compute the `LineInfo` for each element of `tokens`."""
  infos: list[LineInfo] = []

  # Indentation of the current line.  While `line_has_content` is false,
  # this is the count of leading spaces and tabs seen so far.
  indent = 0

  # True if a non-whitespace character has been seen on the current
  # line.
  has_content = False

  for token in tokens:
    text = token.text
    n = len(text)
    pos, indent, has_content = _skip_whitespace(text, 0, indent, has_content)

    if pos == n:
      # Entirely whitespace.  Per the spec, the indentation is computed
      # as if a non-whitespace character followed, and it is first on
      # its line if it has a newline.
      infos.append(LineInfo(indent, _NEWLINE in text))
      continue

    infos.append(LineInfo(indent, not has_content))
    has_content = True

    # If the token spans lines, the state is determined by its last line.
    last_nl = text.rfind(b"\n", pos)
    if last_nl >= 0:
      pos, indent, has_content = _skip_whitespace(text, last_nl, 0, False)
      if pos < n:
        has_content = True

  return infos


def _skip_whitespace(
  text: bytes,
  pos: int,
  indent: int,
  has_content: bool,
) -> tuple[int, int, bool]:
  """
  Skip whitespace in `text` starting at `pos`, updating the `indent` and
  `has_content` line state.  Return the position after the whitespace
  and the updated state.
  """
  n = len(text)
  while pos < n and (c := text[pos]) in _WHITESPACE:
    if c == _NEWLINE:
      indent = 0
      has_content = False
    elif c in _INDENT_CHARS and not has_content:
      indent += 1
    pos += 1
  return pos, indent, has_content


@dataclass
class _Frame:
  """An element of the delimiter stack used by `group_delimiters`."""

  # The opening delimiter, or None for the bottom (root) frame.
  opener: SMToken | None

  # The delimiter kind as a positive number (i.e., this identifes the
  # *closer* kind we expect to match), or 0 for the root frame.
  kind: int

  # Line indentation of the opener.
  indentation: int

  # Nodes that follow the opener so far.
  children: list[TTNode]


def group_delimiters(tokens: list[SMToken], tokenizer: Tokenizer) -> TTNode:
  """
  Perform Phase 2, grouping by delimiters, on `tokens`.  Return the root
  of the resulting token tree.
  """
  infos = compute_line_info(tokens)
  stack: list[_Frame] = [_Frame(None, 0, 0, [])]

  for token, info in zip(tokens, infos):
    kind = tokenizer.delimiter_kind(token)

    if kind < 0:
      # Push a new (as yet) unpaired opener.
      stack.append(_Frame(token, -kind, info.indentation, []))
      continue

    target = _find_opener(stack, kind, info) if kind > 0 else None
    if target is None:
      # Not a delimiter, or an unpaired closer.
      stack[-1].children.append(TTNode.make_token(token))
      continue

    # Convert unpaired openers we've chosen to skip into ordinary
    # tokens.
    while len(stack) - 1 > target:
      _pop_unpaired(stack)

    # Pop the opener that matches closer `token`.
    frame = stack.pop()
    assert frame.opener is not None

    # Build a delimiter group for the matched delimiter pair.
    stack[-1].children.append(TTNode.make_group(
      [TTNode.make_token(frame.opener)] +
        frame.children +
        [TTNode.make_token(token)],
      delim_group=True))

  # At EOF, deal with any openers that never got paired.
  while len(stack) > 1:
    _pop_unpaired(stack)

  # Build and return the root node of the tree.
  return TTNode.make_group(stack[0].children)


def _find_opener(stack: list[_Frame], kind: int, info: LineInfo) -> int | None:
  """
  Return the index in `stack` of the opener that pairs with a closer of
  `kind` and `info`, or None if there is none.
  """
  if info.first_on_line:
    found = _search_stack(stack, kind, info.indentation)
    if found is not None:
      return found

  if stack[-1].kind == kind:
    return len(stack) - 1

  return _search_stack(stack, kind, info.indentation)


def _search_stack(stack: list[_Frame], kind: int, indentation: int) -> int | None:
  """
  Return the index of the topmost opener in `stack` of `kind` and
  `indentation`, or None if there is none.
  """
  for i in range(len(stack) - 1, 0, -1):
    if stack[i].kind == kind and stack[i].indentation == indentation:
      return i
  return None


def _pop_unpaired(stack: list[_Frame]) -> None:
  """
  Pop the top frame of `stack`, whose opener is unpaired, moving the
  opener and its following nodes into the frame below.
  """
  frame = stack.pop()
  assert frame.opener is not None
  parent = stack[-1].children
  parent.append(TTNode.make_token(frame.opener))
  parent.extend(frame.children)


# EOF
