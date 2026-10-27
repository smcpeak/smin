# tokenize_cpp.py
"""
Tokenizer for C and C++.

The tokenizer partitions the input into tokens such that their
concatenation yields the original input.  Whitespace (including
backslash-newline line splices) is included with the following
non-whitespace token, except that whitespace at the end of the input
becomes a token of its own.

The token kinds recognized are:

* Identifiers and keywords.

* Numbers ("preprocessing numbers", which include any suffix).

* String and character literals, including encoding prefixes, raw
  strings, and user-defined literal suffixes.

* Comments, both "//" and "/*...*/".

* Preprocessor directives.  An entire directive, including line splices
  and any "/*...*/" comments within it, is one token, but a trailing
  "//" comment is a separate token.

* Punctuators.  Common multi-character operators like "::" and "->" are
  single tokens.  Delimiters ("(", ")", "[", "]", "{", "}") are always
  single-character tokens.

* Any other byte is a token by itself.

The tokenizer never rejects its input.  For robustness, an unterminated
string or character literal ends at the end of its line, so that stray
apostrophes (e.g., in "#if 0" text) do not swallow subsequent lines.  An
unterminated comment or raw string extends to the end of the input.
"""

from __future__ import annotations

from smin_token import SMToken


_LETTERS = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

# Bytes that can start an identifier.  Bytes 0x80 and above are included
# so that UTF-8 encoded identifiers stay whole.
_IDENT_START: frozenset[int] = frozenset(
  _LETTERS + b"_$" + bytes(range(0x80, 0x100)))

_DIGITS: frozenset[int] = frozenset(b"0123456789")

# Bytes that can continue an identifier.
_IDENT_CONT: frozenset[int] = _IDENT_START | _DIGITS

# Whitespace other than newline.
_HSPACE: frozenset[int] = frozenset(b" \t\r\f\v")

# Bytes that introduce a signed exponent in a number, and the signs.
_EXPONENT_CHARS: frozenset[int] = frozenset(b"eEpP")
_SIGNS: frozenset[int] = frozenset(b"+-")

# Encoding prefixes for string and character literals.
_LITERAL_PREFIXES: frozenset[bytes] = frozenset(
  [b"L", b"u", b"U", b"u8"])

# Prefixes for raw string literals.
_RAW_PREFIXES: frozenset[bytes] = frozenset(
  [b"R", b"LR", b"uR", b"UR", b"u8R"])

# Bytes that cannot appear in a raw string delimiter.
_RAW_DELIM_EXCLUDED: frozenset[int] = frozenset(b"()\\\" \t\r\f\v\n")

# Maximum length of a raw string delimiter.
_RAW_DELIM_MAX_LEN = 16

# Multi-character punctuators, longest first so the first match is the
# longest one.
_PUNCTUATORS: tuple[bytes, ...] = (
  b"<=>", b"<<=", b">>=", b"->*", b"...",
  b"::", b"->", b".*", b"++", b"--", b"<<", b">>", b"<=", b">=",
  b"==", b"!=", b"&&", b"||", b"+=", b"-=", b"*=", b"/=", b"%=",
  b"&=", b"|=", b"^=", b"##",
)

_NEWLINE = ord("\n")
_CR = ord("\r")
_BACKSLASH = ord("\\")
_SLASH = ord("/")
_STAR = ord("*")
_HASH = ord("#")
_DOT = ord(".")
_DQUOTE = ord("\"")
_SQUOTE = ord("'")
_LPAREN = ord("(")

# Map from delimiter byte to its classification; see `delimiter_kind`.
_DELIMITER_KINDS: dict[int, int] = {
  ord("("): -1, ord(")"): 1,
  ord("["): -2, ord("]"): 2,
  ord("{"): -3, ord("}"): 3,
}


def tokenize_cpp(data: bytes) -> list[SMToken]:
  """Partition C/C++ source `data` into tokens."""
  tokens: list[SMToken] = []
  n = len(data)
  pos = 0

  # True if no token has been seen on the current line.
  at_line_start = True

  while pos < n:
    start = pos
    pos, saw_newline = _skip_whitespace(data, pos)
    if saw_newline:
      at_line_start = True
    if pos == n:
      # Whitespace at the end of the input.
      tokens.append(SMToken(data[start:]))
      break

    pos = _scan_token(data, pos, at_line_start)
    tokens.append(SMToken(data[start:pos]))
    at_line_start = False

  return tokens


def delimiter_kind(token: SMToken) -> int:
  """
  Classify `token` as a delimiter.  Return a number in [-3,3] that is
  negative for an opening delimiter, positive for a closing delimiter,
  and zero for a non-delimiter.  Opener -n pairs with closer +n.

  A delimiter token consists of whitespace followed by one delimiter
  byte.  Other tokens that end with a delimiter byte, like "#if (" or
  "// )", are not delimiters.
  """
  text = token.text
  pos, _ = _skip_whitespace(text, 0)
  if pos == len(text) - 1:
    return _DELIMITER_KINDS.get(text[pos], 0)
  return 0


def _splice_len(data: bytes, i: int) -> int:
  """
  Return the length of the line splice (backslash, newline) at `i`, or 0
  if there is none.  The newline may be preceded by a carriage return.
  """
  n = len(data)
  if i < n and data[i] == _BACKSLASH:
    if i+1 < n and data[i+1] == _NEWLINE:
      return 2
    if i+2 < n and data[i+1] == _CR and data[i+2] == _NEWLINE:
      return 3
  return 0


def _skip_whitespace(data: bytes, pos: int) -> tuple[int, bool]:
  """
  Skip whitespace and line splices starting at `pos`.  Return the
  position after them, and whether a newline (other than in a splice)
  was skipped.
  """
  n = len(data)
  saw_newline = False
  while pos < n:
    c = data[pos]
    if c == _NEWLINE:
      saw_newline = True
      pos += 1
    elif c in _HSPACE:
      pos += 1
    elif (splice := _splice_len(data, pos)) > 0:
      pos += splice
    else:
      break
  return pos, saw_newline


def _trim_hspace(data: bytes, start: int, end: int) -> int:
  """Return `end` moved left past whitespace, but not before `start`."""
  while end > start and data[end-1] in _HSPACE:
    end -= 1
  return end


def _scan_token(data: bytes, pos: int, at_line_start: bool) -> int:
  """
  Scan the token that starts with the non-whitespace byte at `pos`, and
  return the position after it.
  """
  n = len(data)
  c = data[pos]
  next_c = data[pos+1] if pos+1 < n else -1

  if c == _HASH and at_line_start:
    return _scan_directive(data, pos)

  if c == _SLASH and next_c == _SLASH:
    return _scan_line_comment(data, pos)

  if c == _SLASH and next_c == _STAR:
    return _scan_block_comment(data, pos)

  if c == _DQUOTE or c == _SQUOTE:
    return _scan_literal_suffix(data, _scan_quoted(data, pos))

  if c in _DIGITS or (c == _DOT and next_c in _DIGITS):
    return _scan_number(data, pos)

  if c in _IDENT_START:
    end = _scan_identifier(data, pos)
    if end < n:
      prefix = data[pos:end]
      if data[end] == _DQUOTE and prefix in _RAW_PREFIXES:
        return _scan_literal_suffix(data, _scan_raw_string(data, end))
      if ((data[end] == _DQUOTE or data[end] == _SQUOTE) and
          prefix in _LITERAL_PREFIXES):
        return _scan_literal_suffix(data, _scan_quoted(data, end))
    return end

  for punct in _PUNCTUATORS:
    if data.startswith(punct, pos):
      return pos + len(punct)

  # Delimiters, single-character operators, and anything else.
  return pos + 1


def _scan_identifier(data: bytes, pos: int) -> int:
  """Scan an identifier starting at `pos`."""
  n = len(data)
  pos += 1
  while pos < n and data[pos] in _IDENT_CONT:
    pos += 1
  return pos


def _scan_literal_suffix(data: bytes, pos: int) -> int:
  """Scan a user-defined literal suffix, if any, starting at `pos`."""
  if pos < len(data) and data[pos] in _IDENT_START:
    return _scan_identifier(data, pos)
  return pos


def _scan_number(data: bytes, pos: int) -> int:
  """
  Scan a preprocessing number starting at `pos`.  This includes digit
  separators, exponents, and suffixes.
  """
  n = len(data)
  pos += 1
  while pos < n:
    c = data[pos]
    next_c = data[pos+1] if pos+1 < n else -1
    if c in _EXPONENT_CHARS and next_c in _SIGNS:
      pos += 2
    elif c in _IDENT_CONT or c == _DOT:
      pos += 1
    elif c == _SQUOTE and next_c in _IDENT_CONT:
      # Digit separator.
      pos += 2
    else:
      break
  return pos


def _scan_quoted(data: bytes, pos: int) -> int:
  """
  Scan a string or character literal whose opening quote is at `pos`.
  An unterminated literal ends just before the end of its line.
  """
  n = len(data)
  quote = data[pos]
  body_start = pos + 1
  pos = body_start
  while pos < n:
    c = data[pos]
    if c == quote:
      return pos + 1
    if c == _NEWLINE:
      return _trim_hspace(data, body_start, pos)
    if c == _BACKSLASH:
      # Skip the escaped character.  A line splice skips the newline.
      pos += _splice_len(data, pos) or 2
    else:
      pos += 1
  return n


def _scan_raw_string(data: bytes, pos: int) -> int:
  """
  Scan a raw string literal whose opening quote is at `pos`.  If the
  delimiter is malformed, scan it as an ordinary string instead.
  """
  n = len(data)
  delim_start = pos + 1
  i = delim_start
  while (i < n and
         i - delim_start <= _RAW_DELIM_MAX_LEN and
         data[i] not in _RAW_DELIM_EXCLUDED):
    i += 1
  if (i < n and
      data[i] == _LPAREN and
      i - delim_start <= _RAW_DELIM_MAX_LEN):
    terminator = b")" + data[delim_start:i] + b"\""
    end = data.find(terminator, i+1)
    return n if end < 0 else end + len(terminator)
  return _scan_quoted(data, pos)


def _scan_line_comment(data: bytes, pos: int) -> int:
  """
  Scan a "//" comment starting at `pos`.  It ends before the newline
  that is not part of a line splice, and excludes trailing whitespace.
  """
  n = len(data)
  i = pos + 2
  while i < n and data[i] != _NEWLINE:
    i += _splice_len(data, i) or 1
  return _trim_hspace(data, pos+2, i)


def _scan_block_comment(data: bytes, pos: int) -> int:
  """Scan a "/*...*/" comment starting at `pos`."""
  end = data.find(b"*/", pos+2)
  return len(data) if end < 0 else end + 2


def _scan_directive(data: bytes, pos: int) -> int:
  """
  Scan a preprocessor directive whose "#" is at `pos`.  It ends before
  the newline that is not part of a line splice or block comment, or
  before a "//" comment, and excludes trailing whitespace.
  """
  n = len(data)
  i = pos + 1
  while i < n:
    c = data[i]
    if c == _NEWLINE:
      break
    if c == _SLASH and i+1 < n and data[i+1] == _SLASH:
      break
    if c == _SLASH and i+1 < n and data[i+1] == _STAR:
      i = _scan_block_comment(data, i)
    elif c == _DQUOTE or c == _SQUOTE:
      i = _scan_quoted(data, i)
    else:
      i += _splice_len(data, i) or 1
  return _trim_hspace(data, pos+1, i)


# EOF
