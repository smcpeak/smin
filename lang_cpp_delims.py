# lang_cpp_delims.py
"""
C++ delimiter codes.
"""

# Codes for each kind of delimiter.
CPP_PAREN = 1
CPP_BRACKET = 2
CPP_BRACE = 3

# Map from delimiter byte to its classification, as stored in
# `SMToken.delimiter_kind`.
CPP_DELIMITER_KINDS: dict[int, int] = {
  ord("("): -CPP_PAREN,   ord(")"): CPP_PAREN,
  ord("["): -CPP_BRACKET, ord("]"): CPP_BRACKET,
  ord("{"): -CPP_BRACE,   ord("}"): CPP_BRACE,
}


# EOF
