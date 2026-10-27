# tokenize_cpp_test.py
"""
Unit tests for tokenize_cpp.
"""

from __future__ import annotations

import random
import unittest

from tokenize_cpp import CPPTokenizer, tokenize_cpp
from tokenizer import Tokenizer


class TokenizeCppTest(unittest.TestCase):
  def check(self, data: bytes, expect: list[bytes]) -> None:
    """Check that `data` tokenizes as `expect`."""
    texts = [t.text for t in tokenize_cpp(data)]
    self.assertEqual(texts, expect)

    # Redundant given the above, but documents the essential invariant.
    self.assertEqual(b"".join(texts), data)

  # ---------------------------- Whitespace ----------------------------
  def test_empty(self) -> None:
    self.check(b"", [])

  def test_only_whitespace(self) -> None:
    self.check(b"  \n\t\n", [b"  \n\t\n"])

  def test_leading_whitespace_attaches_to_next(self) -> None:
    self.check(b"  a\n  b", [b"  a", b"\n  b"])

  def test_trailing_whitespace_token(self) -> None:
    self.check(b"a;\n\n", [b"a", b";", b"\n\n"])

  def test_all_whitespace_kinds(self) -> None:
    self.check(b" \t\r\f\v\na", [b" \t\r\f\v\na"])

  def test_line_splice_is_whitespace(self) -> None:
    self.check(b"a\\\nb", [b"a", b"\\\nb"])
    self.check(b"a\\\r\nb", [b"a", b"\\\r\nb"])

  def test_backslash_not_splice(self) -> None:
    self.check(b"a \\ b", [b"a", b" \\", b" b"])

  # ---------------------- Identifiers and numbers ---------------------
  def test_identifiers(self) -> None:
    self.check(b"int _x9 $y", [b"int", b" _x9", b" $y"])

  def test_utf8_identifier(self) -> None:
    self.check("été x".encode("utf-8"), ["été".encode("utf-8"), b" x"])

  def test_numbers(self) -> None:
    self.check(b"0 42u 0x1F 3.14f 1e10", [
      b"0", b" 42u", b" 0x1F", b" 3.14f", b" 1e10"])

  def test_number_leading_dot(self) -> None:
    self.check(b".5 a.b", [b".5", b" a", b".", b"b"])

  def test_number_signed_exponent(self) -> None:
    self.check(b".5e+10 0x1p-3f 1E-2", [b".5e+10", b" 0x1p-3f", b" 1E-2"])

  def test_number_plus_is_not_exponent(self) -> None:
    self.check(b"1+2", [b"1", b"+", b"2"])

  def test_number_digit_separator(self) -> None:
    self.check(b"1'000'000ULL", [b"1'000'000ULL"])

  def test_number_trailing_apostrophe(self) -> None:
    # Not a digit separator, so the apostrophe starts a character
    # literal that is unterminated.
    self.check(b"1';", [b"1", b"';"])

  def test_number_at_eof(self) -> None:
    self.check(b"1e", [b"1e"])

  # ----------------------------- Literals -----------------------------
  def test_string(self) -> None:
    self.check(b'x = "a b";', [b"x", b" =", b' "a b"', b";"])

  def test_string_escapes(self) -> None:
    self.check(b'"a\\"b\\\\" c', [b'"a\\"b\\\\"', b" c"])

  def test_string_containing_comment_markers(self) -> None:
    self.check(b'"// /*" x', [b'"// /*"', b" x"])

  def test_string_with_line_splice(self) -> None:
    self.check(b'"a\\\nb" c', [b'"a\\\nb"', b" c"])
    self.check(b'"a\\\r\nb" c', [b'"a\\\r\nb"', b" c"])

  def test_char_literals(self) -> None:
    self.check(b"'a' '\\'' '\"'", [b"'a'", b" '\\''", b" '\"'"])

  def test_literal_prefixes(self) -> None:
    self.check(b"L\"a\" u8\"b\" u'c' U'd'", [
      b'L"a"', b' u8"b"', b" u'c'", b" U'd'"])

  def test_non_prefix_identifier_before_string(self) -> None:
    self.check(b'f"a"', [b"f", b'"a"'])

  def test_user_defined_literal_suffix(self) -> None:
    self.check(b'"abc"_sv \'x\'_c;', [b'"abc"_sv', b" 'x'_c", b";"])

  def test_raw_string(self) -> None:
    self.check(b'R"(a\n"b)" x', [b'R"(a\n"b)"', b" x"])

  def test_raw_string_with_delimiter(self) -> None:
    self.check(b'u8R"xy(a)"b)xy"_sv;', [b'u8R"xy(a)"b)xy"_sv', b";"])

  def test_raw_string_bad_delimiter(self) -> None:
    # A space cannot appear in the delimiter, so this is scanned as an
    # ordinary string.
    self.check(b'R"a b(x)a b" y', [b'R"a b(x)a b"', b" y"])

  def test_raw_string_delimiter_too_long(self) -> None:
    delim = b"d" * 17
    data = b'R"' + delim + b'(x)' + delim + b'"'
    self.check(data, [data])

  # ------------------------ Malformed literals ------------------------
  def test_unterminated_string_ends_at_line_end(self) -> None:
    self.check(b'"abc\nx;', [b'"abc', b"\nx", b";"])

  def test_unterminated_string_excludes_cr(self) -> None:
    self.check(b'"abc\r\nx', [b'"abc', b"\r\nx"])

  def test_unterminated_string_at_eof(self) -> None:
    self.check(b'"abc', [b'"abc'])
    self.check(b'"\\', [b'"\\'])

  def test_stray_apostrophe(self) -> None:
    self.check(b"#if 0\ndon't do this\n#endif\n", [
      b"#if 0", b"\ndon", b"'t do this", b"\n#endif", b"\n"])

  def test_unterminated_raw_string(self) -> None:
    self.check(b'R"(abc\n\nx', [b'R"(abc\n\nx'])

  def test_raw_prefix_at_eof(self) -> None:
    self.check(b'R"', [b'R"'])
    self.check(b'R"abc', [b'R"abc'])

  # ----------------------------- Comments -----------------------------
  def test_line_comment(self) -> None:
    self.check(b"a; // c\nb;", [b"a", b";", b" // c", b"\nb", b";"])

  def test_line_comment_excludes_trailing_whitespace(self) -> None:
    self.check(b"// c  \r\nx", [b"// c", b"  \r\nx"])

  def test_line_comment_with_splice(self) -> None:
    self.check(b"// a\\\nb\nc", [b"// a\\\nb", b"\nc"])

  def test_line_comment_at_eof(self) -> None:
    self.check(b"// c", [b"// c"])

  def test_block_comment(self) -> None:
    self.check(b"a /* b\n c */ d", [b"a", b" /* b\n c */", b" d"])

  def test_block_comment_not_nested(self) -> None:
    self.check(b"/* /* */ */", [b"/* /* */", b" *", b"/"])

  def test_unterminated_block_comment(self) -> None:
    self.check(b"a /* b\nc", [b"a", b" /* b\nc"])

  # ---------------------- Preprocessor directives ---------------------
  def test_directive(self) -> None:
    self.check(b"#include <iostream>\nint", [b"#include <iostream>", b"\nint"])

  def test_directive_indented(self) -> None:
    self.check(b"  # define X 1\n", [b"  # define X 1", b"\n"])

  def test_directive_trailing_line_comment(self) -> None:
    self.check(b"#include <iostream>        // std::cout\n", [
      b"#include <iostream>", b"        // std::cout", b"\n"])

  def test_directive_with_splice(self) -> None:
    self.check(b"#define X \\\n  1\nx", [b"#define X \\\n  1", b"\nx"])

  def test_directive_with_block_comment(self) -> None:
    self.check(b"#define X /* a\nb */ 1\nx", [
      b"#define X /* a\nb */ 1", b"\nx"])

  def test_directive_with_string(self) -> None:
    self.check(b'#define S "//" \'"\'\nx', [b'#define S "//" \'"\'', b"\nx"])

  def test_directive_excludes_trailing_whitespace(self) -> None:
    self.check(b"#endif  \r\nx", [b"#endif", b"  \r\nx"])

  def test_directive_ending_in_splice(self) -> None:
    self.check(b"#define X \\\n\nx", [b"#define X \\\n", b"\nx"])

  def test_hash_not_at_line_start(self) -> None:
    self.check(b"a # b ## c", [b"a", b" #", b" b", b" ##", b" c"])

  def test_hash_after_comment_not_directive(self) -> None:
    self.check(b"/**/ #x\n", [b"/**/", b" #", b"x", b"\n"])

  def test_directive_at_eof(self) -> None:
    self.check(b"#", [b"#"])
    self.check(b"#endif", [b"#endif"])

  # --------------------------- Punctuators ----------------------------
  def test_delimiters_are_single(self) -> None:
    self.check(b"({[]})", [b"(", b"{", b"[", b"]", b"}", b")"])

  def test_double_brackets_split(self) -> None:
    self.check(b"[[nodiscard]]", [
      b"[", b"[", b"nodiscard", b"]", b"]"])

  def test_multi_char_punctuators(self) -> None:
    self.check(b"a::b->c <=> d <<= e ...", [
      b"a", b"::", b"b", b"->", b"c", b" <=>", b" d", b" <<=", b" e",
      b" ..."])

  def test_longest_punctuator_match(self) -> None:
    self.check(b"->*", [b"->*"])
    self.check(b"<<<", [b"<<", b"<"])

  def test_closing_template_brackets(self) -> None:
    self.check(b"v<v<int>>", [b"v", b"<", b"v", b"<", b"int", b">>"])

  def test_single_char_punctuators(self) -> None:
    self.check(b"**p", [b"*", b"*", b"p"])

  def test_other_bytes(self) -> None:
    self.check(b"@ ` \x01", [b"@", b" `", b" \x01"])

  # ----------------------------- Overall ------------------------------
  def test_hello_world(self) -> None:
    self.check(
      b'#include <iostream>        // std::cout\n'
      b'\n'
      b'int main(int argc, char **argv)\n'
      b'{\n'
      b'  std::cout << "Hello\\n";\n'
      b'  return 0;\n'
      b'}\n',
      [
        b"#include <iostream>", b"        // std::cout",
        b"\n\nint", b" main", b"(", b"int", b" argc", b",", b" char",
        b" *", b"*", b"argv", b")",
        b"\n{",
        b"\n  std", b"::", b"cout", b" <<", b' "Hello\\n"', b";",
        b"\n  return", b" 0", b";",
        b"\n}",
        b"\n",
      ])

  def test_random_round_trip(self) -> None:
    # Random inputs drawn from bytes that are significant to the
    # tokenizer must always be partitioned into non-empty tokens.
    rng = random.Random(1)
    alphabet = b"ab1._'\"/*\\\n\r #(){}[]<>=-+eRu8xp"
    for _ in range(5000):
      data = bytes(rng.choice(alphabet) for _ in range(rng.randint(0, 30)))
      texts = [t.text for t in tokenize_cpp(data)]
      self.assertEqual(b"".join(texts), data)
      self.assertTrue(all(texts), data)


class DelimiterKindTest(unittest.TestCase):
  def kinds(self, data: bytes) -> list[int]:
    """Return the delimiter kinds of the tokens of `data`."""
    return [t.delimiter_kind for t in tokenize_cpp(data)]

  def test_openers(self) -> None:
    self.assertEqual(self.kinds(b"( [ {"), [-1, -2, -3])

  def test_closers(self) -> None:
    self.assertEqual(self.kinds(b") ] }"), [1, 2, 3])

  def test_leading_whitespace(self) -> None:
    self.assertEqual(self.kinds(b"\n  { \t\r\f\v\n)"), [-3, 1])

  def test_leading_line_splice(self) -> None:
    self.assertEqual(self.kinds(b"\\\n] \\\r\n ["), [2, -2])

  def test_non_delimiters(self) -> None:
    self.assertEqual(
      self.kinds(b"a < > >> ; :: 0 \"a\" '('"),
      [0] * 9)

  def test_eof_whitespace(self) -> None:
    self.assertEqual(self.kinds(b"(\n"), [-1, 0])

  def test_ends_with_delimiter_byte(self) -> None:
    # Tokens that contain or end with a delimiter byte but are not
    # delimiters.
    for data in [b"#if (", b"#define F(a)", b"// {", b"/* } */",
                 b'R"(x)"', b'")"']:
      with self.subTest(data=data):
        self.assertEqual(self.kinds(data), [0])

  def test_tokenized_input(self) -> None:
    self.assertEqual(self.kinds(b"f(a[i]) {\n  g();\n}\n"), [
      0, -1, 0, -2, 0, 2, 1,       # f(a[i])
      -3, 0, -1, 1, 0, 3,          # {\n  g();\n}
      0,                           # \n
    ])


class LineAttributesTest(unittest.TestCase):
  def attrs(self, data: bytes) -> list[tuple[bytes, int, bool]]:
    """
    Return the text, indentation, and first-on-line flag of each token
    of `data`.
    """
    return [(t.text, t.indentation, t.first_on_line)
            for t in tokenize_cpp(data)]

  def test_first_token(self) -> None:
    self.assertEqual(self.attrs(b"a"), [(b"a", 0, True)])
    self.assertEqual(self.attrs(b"  a"), [(b"  a", 2, True)])

  def test_same_line(self) -> None:
    self.assertEqual(self.attrs(b"  a b;"), [
      (b"  a", 2, True), (b" b", 2, False), (b";", 2, False)])

  def test_new_lines(self) -> None:
    self.assertEqual(self.attrs(b"a\n\t b c\n\nd"), [
      (b"a", 0, True), (b"\n\t b", 2, True), (b" c", 2, False),
      (b"\n\nd", 0, True)])

  def test_tabs_count_as_one(self) -> None:
    self.assertEqual(self.attrs(b"\t\ta"), [(b"\t\ta", 2, True)])

  def test_other_whitespace_counted(self) -> None:
    self.assertEqual(self.attrs(b"\f\v a"), [(b"\f\v a", 3, True)])

  def test_multi_line_token(self) -> None:
    # A token that begins on the last line of a multi-line token is not
    # first on its line, and has that line's indentation.
    self.assertEqual(self.attrs(b"  /* a\n    b */ c\nd"), [
      (b"  /* a\n    b */", 2, True), (b" c", 4, False),
      (b"\nd", 0, True)])

  def test_multi_line_directive(self) -> None:
    self.assertEqual(self.attrs(b"#define X \\\n  1\n x"), [
      (b"#define X \\\n  1", 0, True), (b"\n x", 1, True)])

  def test_line_splice_starts_physical_line(self) -> None:
    self.assertEqual(self.attrs(b"a \\\n  b"), [
      (b"a", 0, True), (b" \\\n  b", 2, True)])

  def test_eof_whitespace(self) -> None:
    self.assertEqual(self.attrs(b"a\n  "), [
      (b"a", 0, True), (b"\n  ", 2, True)])
    self.assertEqual(self.attrs(b"  a  "), [
      (b"  a", 2, True), (b"  ", 2, False)])

  def test_only_whitespace(self) -> None:
    self.assertEqual(self.attrs(b"  "), [(b"  ", 2, False)])
    self.assertEqual(self.attrs(b"\n  "), [(b"\n  ", 2, True)])


class LastOnLineTest(unittest.TestCase):
  def last(self, data: bytes) -> list[tuple[bytes, bool]]:
    """Return the text and last-on-line flag of each token of `data`."""
    return [(t.text, t.last_on_line) for t in tokenize_cpp(data)]

  def test_single_token(self) -> None:
    self.assertEqual(self.last(b"a"), [(b"a", True)])

  def test_same_line(self) -> None:
    self.assertEqual(self.last(b"a b;\nc"), [
      (b"a", False), (b" b", False), (b";", True), (b"\nc", True)])

  def test_trailing_whitespace(self) -> None:
    self.assertEqual(self.last(b"a \t\r\nb"), [
      (b"a", True), (b" \t\r\nb", True)])

  def test_followed_by_comment(self) -> None:
    self.assertEqual(self.last(b"a; // c\nb"), [
      (b"a", False), (b";", False), (b" // c", True), (b"\nb", True)])

  def test_multi_line_token(self) -> None:
    # The relevant line is the one containing the token's last character.
    self.assertEqual(self.last(b"/* a\nb */\nc /* d\ne */ f"), [
      (b"/* a\nb */", True), (b"\nc", False), (b" /* d\ne */", False),
      (b" f", True)])

  def test_token_ending_with_newline(self) -> None:
    # A directive can end with a line splice.  Its last character is the
    # newline, so nothing follows it on its line.
    self.assertEqual(self.last(b"#define X \\\n\nx"), [
      (b"#define X \\\n", True), (b"\nx", True)])

  def test_followed_by_line_splice(self) -> None:
    # A line splice is whitespace, and its newline ends the line.
    self.assertEqual(self.last(b"a \\\n  b"), [
      (b"a", True), (b" \\\n  b", True)])
    self.assertEqual(self.last(b"a\\\r\nb"), [
      (b"a", True), (b"\\\r\nb", True)])

  def test_backslash_not_splice(self) -> None:
    self.assertEqual(self.last(b"a \\ b"), [
      (b"a", False), (b" \\", False), (b" b", True)])

  def test_eof_whitespace(self) -> None:
    self.assertEqual(self.last(b"a\n"), [(b"a", True), (b"\n", False)])
    self.assertEqual(self.last(b"a  "), [(b"a", True), (b"  ", False)])
    self.assertEqual(self.last(b"  "), [(b"  ", False)])


class CPPTokenizerTest(unittest.TestCase):
  def test_via_protocol(self) -> None:
    # The annotation makes mypy check that CPPTokenizer conforms.
    tokenizer: Tokenizer = CPPTokenizer()
    tokens = tokenizer.tokenize(b"f(x);")
    self.assertEqual([t.text for t in tokens], [b"f", b"(", b"x", b")", b";"])
    self.assertEqual([t.delimiter_kind for t in tokens], [0, -1, 0, 1, 0])


if __name__ == "__main__":
  unittest.main()


# EOF
