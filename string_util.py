# string_util.py
"""
String utilities.
"""

from __future__ import annotations


_SIMPLE_ESCAPES: dict[int, str] = {
  ord("\n"): "\\n",
  ord("\t"): "\\t",
  ord("\r"): "\\r",
  ord("\""): "\\\"",
  ord("\\"): "\\\\",
}


def quote_bytes(data: bytes) -> str:
  """Quote `data` as a C-style string literal.

  Non-printable bytes use three-digit octal escapes, which, unlike
  `\\x`, cannot absorb a following character into the escape.
  """
  out = ['"']
  for b in data:
    if b in _SIMPLE_ESCAPES:
      out.append(_SIMPLE_ESCAPES[b])
    elif 0x20 <= b < 0x7F:
      out.append(chr(b))
    else:
      out.append(f"\\{b:03o}")
  out.append('"')
  return "".join(out)


# EOF
