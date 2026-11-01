# minimizer.py
"""
Minimizer algorithm class.

See minimization-algorithm.txt.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional

from abstract_range import AbstractRange
from acceptance_test_result import AcceptanceTestResult
from byte_range import ByteRange
from smin_token import SMToken
from start_report import TestStartReport
from token_tree import TTNode


# Bytes regarded as whitespace when rendering candidates.
_WHITESPACE: frozenset[int] = frozenset(b" \t\r\f\v\n")

_NEWLINE: int = ord("\n")


# Signature of a function that can specify non-trivial replacement text
# for a node.  If it returns None, then the only replacement is the
# empty byte sequence.  If it returns non-None, then *in addition* to
# replacement by the empty sequence, we also consider replacing the node
# with the specified sequence.
NTReplacementFunc = Callable[[TTNode], Optional[bytes]]


# Signature of a function that checks a candidate input for acceptance
# as "interesting" for minimization purposes.  The second argument is
# the progress report for the candidate.  In normal operation, this
# spawns a new process to run an external program, and waits for it to
# terminate.
AcceptanceTestFunc = Callable[[bytes, TestStartReport], AcceptanceTestResult]


# Signature of a function that accepts a test start report.  In normal
# operation, the callee prints this data to the console.
TestStartReportFunc = Callable[[TestStartReport], None]

# Signature of a function called when a test finishes.  The second
# argument is True if the result came from the memoization table rather
# than running the test.  Again, this is normally just printed to the
# console.
TestFinishedReportFunc = Callable[[AcceptanceTestResult, bool], None]


class _TokenRange(AbstractRange):
  """
  Describes a contiguous sequence of tokens, identified by their indices
  into `Minimizer.tokens`.
  """

  # Reminder: AbstractRange has `start` and `stop` members.


@dataclass
class _AffectedByteRange:
  """
  Describes the range of bytes in the rendered candidate that are
  potentially different from those in the last accepted input.  This is
  used to compute the CHANGED_BYTE_RANGE that is passed to the candidate
  acceptance test program.
  """

  # TODO: Improve these field names.

  # Byte offset in the rendered candidate at the point we begin rendering
  # the first token in the affected token range.  The rendered candidate
  # before `entry` is the same as that of the last accepted input.
  entry: int

  # Byte offset in the rendered candidate where the first live token
  # after the affected token range has its first non-whitespace
  # character; or None if there is no such token.  The rendered
  # candidate after `sync` is the same as that of the last accepted
  # input.  (The candidate does not necessarily sync up at the end of
  # the affected tokens, since the whitespace that precedes the next
  # live token depends on the preceding gap.)
  sync: Optional[int]


class Minimizer:
  """Minimize a token tree w.r.t. a given acceptance test."""

  # ---- Input ----
  # The root of the token tree representing the original input.
  tree_root: TTNode

  # Query for non-trivial replacement text for a node.
  get_non_trivial_replacement: NTReplacementFunc

  # Check if a given candidate is accepted.  In normal operation, this
  # will start a child process.
  test_acceptance: AcceptanceTestFunc

  # ---- Progress callbacks ----
  # Called before starting a test.
  report_test_starting: TestStartReportFunc

  # Called when a test finishes.
  report_test_finished: TestFinishedReportFunc

  # ---- Fixed data derived from the input ----
  # The tokens of the original input, in order.  Tokens are identified
  # by their index in this list.
  tokens: list[SMToken]

  # True if the original input ends with a newline, in which case every
  # rendered candidate does too.
  ends_with_newline: bool

  # Map from the id() of each node to the range of the tokens it
  # contains.
  node_span: dict[int, _TokenRange]

  # ---- Mutable algorithm data ----
  # Map from the id() of a TTNode to its replacement text.  (The key is
  # the identity because TTNode is not hashable.)  Only nodes that have
  # been replaced are present in the map.  When `run_minimizer`
  # terminates, this holds the data needed to construct the final
  # minimized and accepted candidate.
  #
  # This is only ever modified by a single `update` call per accepted
  # candidate, so that if Ctrl-C interrupts the minimizer's own work, it
  # still describes an accepted input.
  cur_replacement: dict[int, bytes]

  # For each token index, True if the token is live, i.e., neither it
  # nor any ancestor has been replaced.  This is derived from
  # `cur_replacement`, for efficiency.
  token_live: list[bool]

  # Number of True elements in `token_live`.
  live_tok_count: int

  # Size in bytes of the most recently accepted input.
  accepted_size: int

  # Map from the 16-byte MD5 digest of a candidate input to its outcome,
  # for a candidate that has already been tested.  The INTERRUPTED
  # outcome is never stored here.
  memoized_accept: dict[bytes, AcceptanceTestResult]

  # Initially False, this is set to true by `run_minimizer`, and used to
  # check that that function is only invoked once.
  minimizer_invoked: bool

  # ---- Progress data ----
  # Number of candidates reported so far, including those whose verdict
  # was found in the memoization table.
  sequence_num: int

  # Number of passes the algorithm will make.
  total_num_passes: int

  # Index of the current pass, starting at 0.  The granularity of pass
  # k is `len(tokens) / 2**k`.
  pass_index: int


  def __init__(
    self,
    tree_root: TTNode,
    get_non_trivial_replacement: NTReplacementFunc,
    test_acceptance: AcceptanceTestFunc,
    report_test_starting: TestStartReportFunc,
    report_test_finished: TestFinishedReportFunc,
    max_passes: Optional[int] = None,
  ) -> None:
    """
    Prepare to minimize the input represented by `tree_root`.  If
    `max_passes` is not None, make at most that many passes.

    Requires that the acceptance test has already accepted that input.
    """

    self.tree_root = tree_root
    self.get_non_trivial_replacement = get_non_trivial_replacement
    self.test_acceptance = test_acceptance
    self.report_test_starting = report_test_starting
    self.report_test_finished = report_test_finished

    self.tokens = list(tree_root.tokens())
    self.node_span = {}
    end = self._compute_spans(tree_root, 0)
    assert end == len(self.tokens)
    self.ends_with_newline = (
      len(self.tokens) > 0 and self.tokens[-1].text.endswith(b"\n"))

    self.cur_replacement = {}
    self.token_live = [True] * len(self.tokens)
    self.live_tok_count = len(self.tokens)
    self.minimizer_invoked = False

    self.sequence_num = 0

    # This is floor(log_2(S))+1 for S > 0, and 0 for S = 0.
    self.total_num_passes = len(self.tokens).bit_length()
    if max_passes is not None:
      self.total_num_passes = min(self.total_num_passes, max_passes)
    self.pass_index = 0

    initial_text = self.render_candidate({})
    self.accepted_size = len(initial_text)
    self.memoized_accept = {
      _digest(initial_text): AcceptanceTestResult.ACCEPT,
    }


  def run_minimizer(self) -> AcceptanceTestResult:
    """
    Run the main minimizer algorithm.

    Requires that `run_minimizer` has not been invoked previously.

    It returns ACCEPT if we reached the end of the algorithm normally,
    and INTERRUPTED otherwise.
    """

    assert not self.minimizer_invoked
    self.minimizer_invoked = True

    try:
      for k in range(self.total_num_passes):
        self.pass_index = k
        self._minimize_node(self.tree_root)
    except _StopMinimization as e:
      return e.result

    return AcceptanceTestResult.ACCEPT


  def get_minimized_test_input(self) -> bytes:
    """
    Return the most recently accepted test input, i.e., the primary
    output of the minimizer.

    Requires that `run_minimizer` has been invoked.
    """

    assert self.minimizer_invoked
    return self.render_candidate({})


  def current_tok_count(self) -> int:
    """
    Return the number of live tokens in the most recently accepted
    input.  Unlike `live_tok_count`, this is computed from
    `cur_replacement` alone, so it is accurate even if Ctrl-C
    interrupted the update of `token_live`.
    """
    ctm: list[bytes | None] = [None] * len(self.tokens)
    self._fill_ctm(self.tree_root, {}, ctm)
    return ctm.count(None)


  def render_candidate(self, extra: dict[int, bytes]) -> bytes:
    """
    Render the input with the current replacements, plus those in
    `extra`, which maps a node's id() to its candidate replacement.
    The result ends with a newline if the original input did.
    """
    return self.render_candidate_with_range(extra)[0]


  def render_candidate_with_range(
    self,
    extra: dict[int, bytes],
  ) -> tuple[bytes, Optional[ByteRange]]:
    """
    Render the candidate as `render_candidate` does, and also return
    the range of bytes in the most recently accepted input that were
    modified to produce it, or None if `extra` is empty.  The bytes
    before and after that range are the same in the candidate.
    """

    # Candidate Token Map (CTM): for each token, None if it is live, and
    # otherwise its replacement text.  (See minimization-algorithm.txt,
    # "Candidate rendering".)
    ctm: list[Optional[bytes]] = [None] * len(self.tokens)
    affected_token_range: Optional[_TokenRange] = (
      self._fill_ctm(self.tree_root, extra, ctm))

    # Render the candidate using the CTM.
    text: bytes
    affected_byte_range: Optional[_AffectedByteRange]
    text, affected_byte_range = (
      _render_ctm([t.text for t in self.tokens],
                  ctm,
                  affected_token_range))

    # Ensure the candidate ends with a newline (if the original did)
    # since working with files that do not is annoying.
    if self.ends_with_newline and not text.endswith(b"\n"):
      text += b"\n"

    if affected_byte_range is None:
      return text, None

    # The candidate and the accepted input agree after `sync`, so the
    # end of the modified range is that far from the end of the latter.
    stop: int = (
      self.accepted_size if affected_byte_range.sync is None
      else self.accepted_size - (len(text) - affected_byte_range.sync))
    assert affected_byte_range.entry <= stop  # TODO: Obviate with AbstractRange assertion.
    return text, ByteRange(affected_byte_range.entry, stop)


  def node_size(self, node: TTNode) -> int:
    """Return the number of live tokens in `node`."""
    span = self.node_span[id(node)]
    return sum(self.token_live[span.start : span.stop])


  def _compute_spans(self, node: TTNode, start: int) -> int:
    """
    Populate `node_span` for `node` and its descendants, given that its
    first token has index `start`.  Return the index after its last
    token.
    """
    if node.token is not None:
      end = start + 1
    else:
      end = start
      for child in node.children:
        end = self._compute_spans(child, end)
    self.node_span[id(node)] = _TokenRange(start, end)
    return end


  def _fill_ctm(
    self,
    node: TTNode,
    extra: dict[int, bytes],
    ctm: list[bytes | None],
  ) -> Optional[_TokenRange]:
    """
    Record in `ctm` the replacements of `node` and its descendants.  A
    replacement on a node overrides any on its descendants.

    Return the smallest range of tokens that contains every node
    replaced by `extra`, or None if there are none.
    """
    replacement = extra.get(id(node))
    affected: Optional[_TokenRange] = None
    if replacement is not None:
      affected = self.node_span[id(node)]
    else:
      replacement = self.cur_replacement.get(id(node))

    if replacement is not None:
      span = self.node_span[id(node)]
      if span.start < span.stop:
        ctm[span.start] = replacement
        for i in range(span.start+1, span.stop):
          ctm[i] = b""
    else:
      for child in node.children:
        child_affected = self._fill_ctm(child, extra, ctm)
        if child_affected is not None:
          affected = (child_affected if affected is None
                      else affected.union(child_affected))

    return affected


  def _exceeds_half_granularity(self, size: int) -> bool:
    """True if `size` > G/2."""
    # G/2 = S / 2**(k+1), so compare using integers.
    return (size << (self.pass_index + 1)) > len(self.tokens)

  def _exceeds_granularity(self, size: int) -> bool:
    """True if `size` > G."""
    return (size << self.pass_index) > len(self.tokens)


  def _minimize_node(self, parent: TTNode) -> None:
    """
    Try to replace the children of `parent`, recursively, scanning them
    from last to first.
    """

    # This can only happen if the root is a token, which the structure
    # deduction algorithm does not produce.
    if parent.token is not None:
      return

    # Range [lo, hi) of children to consider, excluding delimiters.
    children = parent.children
    lo, hi = (1, len(children)-1) if parent.delim_group else (0, len(children))

    # Index in `children` of the next node to process.  It walks the
    # list backwards.
    i = hi - 1

    while i >= lo:
      node = children[i]

      # Skip dead nodes.
      if id(node) in self.cur_replacement:
        i -= 1
        continue

      size = self.node_size(node)

      if self._exceeds_half_granularity(size):
        # Case 1: Try replacing the entire node.
        if not self._try_replace_single(node):
          if self._exceeds_granularity(size):
            # Case 2: Also try replacing its children.
            self._minimize_node(node)
        i -= 1
        continue

      # Case 3: Accumulate a run of small nodes, ending with `node`.
      run = [node]
      run_size = size
      j = i - 1
      while j >= lo:
        prev = children[j]

        # Skip dead nodes.
        if id(prev) not in self.cur_replacement:
          prev_size = self.node_size(prev)

          # Stop accumulating if `prev` is big enough that we want to
          # try removing it in isolation, or if adding it to the run
          # would make that run larger than the current granularity.
          if (self._exceeds_half_granularity(prev_size) or
              self._exceeds_granularity(run_size + prev_size)):
            break

          run.append(prev)
          run_size += prev_size

        j -= 1

      if len(run) == 1:
        self._try_replace_single(node)
      else:
        # When we try removing a run, we only try the trivial
        # replacement of an empty byte sequence.
        self._try_candidate({id(n): b"" for n in run}, run)

      # Continue with the node that stopped the run, if any.
      i = j


  def _try_replace_single(self, node: TTNode) -> bool:
    """
    Try replacing `node` with the empty sequence, then, if that fails,
    with its non-trivial replacement, if any.  Return True if either
    was accepted.
    """
    if self._try_candidate({id(node): b""}, [node]):
      return True

    replacement = self.get_non_trivial_replacement(node)
    if replacement:
      return self._try_candidate({id(node): replacement}, [node])

    return False


  def _try_candidate(
    self,
    extra: dict[int, bytes],
    nodes: list[TTNode],
  ) -> bool:
    """
    Test the candidate formed by adding the replacements in `extra`,
    which replace `nodes`, to the current ones.  If it is accepted, make
    them current and return True.
    """
    text: bytes
    changed: Optional[ByteRange]
    text, changed = self.render_candidate_with_range(extra)
    assert changed is not None
    digest: bytes = _digest(text)

    self.sequence_num += 1
    report = self._make_report(nodes, changed)
    self.report_test_starting(report)

    result: Optional[AcceptanceTestResult] = self.memoized_accept.get(digest)
    if result is not None:
      self.report_test_finished(result, True)
    else:
      result = self.test_acceptance(text, report)
      self.report_test_finished(result, False)
      if result == AcceptanceTestResult.INTERRUPTED:
        raise _StopMinimization(result)
      self.memoized_accept[digest] = result

    if result != AcceptanceTestResult.ACCEPT:
      return False

    self.accepted_size = len(text)
    self._commit(extra)
    return True


  def _commit(self, extra: dict[int, bytes]) -> None:
    """Make the replacements in `extra` current."""
    self.cur_replacement.update(extra)

    for key in extra:
      span = self.node_span[key]
      for i in range(span.start, span.stop):
        if self.token_live[i]:
          self.token_live[i] = False
          self.live_tok_count -= 1

    if self.live_tok_count == 0:
      # Nothing is left to remove.
      raise _StopMinimization(AcceptanceTestResult.ACCEPT)


  def _make_report(
    self,
    nodes: list[TTNode],
    changed: ByteRange,
  ) -> TestStartReport:
    """
    Make the report for a test of the candidate replacing `nodes`, which
    modifies the `changed` bytes of the most recently accepted input.
    """

    # `e` (called "E" in the spec) is the 1-based index, among the live
    # tokens, of the last live token in the candidate, or of the live
    # token to its left if it has none.  Either way, it is the number of
    # live tokens before the end of the rightmost node.
    end = max(self.node_span[id(n)].stop for n in nodes)
    e = sum(self.token_live[:end])

    num_live = self.live_tok_count

    return TestStartReport(
      sequence_num=self.sequence_num,
      last_accepted_tok_count=num_live,
      pass_num=self.pass_index + 1,
      total_num_passes=self.total_num_passes,
      granularity=len(self.tokens) / (1 << self.pass_index),
      completion_fraction=(num_live - e) / num_live,
      removed_tok_count=sum(self.node_size(n) for n in nodes),
      initial_tok_count=len(self.tokens),
      changed_byte_range=changed,
    )


class _StopMinimization(Exception):
  """Raised to unwind the recursion when minimization stops early."""

  def __init__(self, result: AcceptanceTestResult) -> None:
    super().__init__(result.name)
    self.result = result


def _digest(data: bytes) -> bytes:
  """Return the MD5 digest of `data`."""
  return hashlib.md5(data, usedforsecurity=False).digest()


def _leading_ws(s: bytes) -> bytes:
  """Return the whitespace at the start of `s`."""
  i = 0
  while i < len(s) and s[i] in _WHITESPACE:
    i += 1
  return s[:i]


def _trail_indent(s: bytes) -> bytes:
  """
  Return the last newline in `s` followed by the whitespace that
  immediately follows it, or the empty sequence if `s` has no newline.
  """
  start = s.rfind(b"\n")
  if start < 0:
    return b""
  return _leading_ws(s[start:])


def _render_ctm(
  texts: list[bytes],
  ctm: list[bytes | None],
  affected_token_range: Optional[_TokenRange],
) -> tuple[bytes, Optional[_AffectedByteRange]]:
  """
  Render the candidate where token i has original text `texts[i]`, and
  is live if `ctm[i]` is None, and otherwise replaced by `ctm[i]`.

  See minimization-algorithm.txt, "Candidate rendering".

  If `affected_token_range` is not None, it is the range of the tokens
  whose replacements differ from those of the accepted input, and this
  function computes and return the corresponding range of affected
  bytes.

  If (and only if) `affected_token_range` is None, the second returned
  element is also None.
  """

  # TODO: Turn this into an assertion in the AbstractRange ctor.
  if affected_token_range is not None:
    assert affected_token_range.start <= affected_token_range.stop

  # Rendered output as a sequence of token texts.  Like the tokens in
  # the token tree, the token texts here may have leading whitespace.
  #
  # TODO: Rename this to `candidate`.
  out: list[bytes] = []

  # Affected candidate offsets to return, once known.
  affected_byte_range: Optional[_AffectedByteRange] = None

  # True once a live token has been emitted, i.e., there is an "A".
  seen_live = False

  # True if there is a gap of dead tokens since the last live token (or
  # the start of the input).
  in_gap = False

  # Texts of the dead tokens with trivial replacements since the end of
  # the last piece.
  trivial: list[bytes] = []

  for i, (text, replacement) in enumerate(zip(texts, ctm, strict=True)):
    if (affected_token_range is not None and
        i == affected_token_range.start):
      # We just crossed into the affected region, so record the size of
      # what has been rendered so far to `out`.
      affected_byte_range = _AffectedByteRange(
        entry = sum(map(len, out)),
        sync  = None)

    if replacement is None:
      if not in_gap:
        out.append(text)

      else:
        # This is B, the end of the last piece of the gap.
        ws = _leading_ws(text)
        indent = _trail_indent(b"".join(trivial))
        if _NEWLINE in ws:
          out.append(text)
        elif indent:
          out.append(indent + text[len(ws):])
        elif not ws and seen_live:
          out.append(b" " + text)
        else:
          out.append(text)
        trivial = []
        in_gap = False

      seen_live = True

      if (affected_token_range is not None and
          i >= affected_token_range.stop):
        # We should have already created the ABR.
        assert affected_byte_range is not None

        if affected_byte_range.sync is None:
          # Current `out` length.
          out_len_bytes: int = sum(map(len, out))

          # Length of after-first-whitespace byte sequence that was just
          # added for the current token.
          len_after_ws: int = len(text) - len(_leading_ws(text))

          # Only the whitespace emitted before this token's own
          # non-whitespace text can differ from the last accepted input.
          affected_byte_range.sync = out_len_bytes - len_after_ws

    else:
      in_gap = True
      if replacement:
        # End of a piece with a non-trivial replacement.
        out.append(
          _trail_indent(b"".join(trivial) + _leading_ws(text)) +
          replacement)
        trivial = []
      else:
        trivial.append(text)

  # Any trivially replaced tokens at the end are discarded.
  text = b"".join(out)

  if affected_token_range is None:
    return text, None

  # TODO: Can this assertion ever fail?
  assert affected_byte_range is not None
  if affected_byte_range is None:
    # We never crossed into the affected range, so return an effectively
    # empty byte range.
    affected_byte_range = _AffectedByteRange(
      entry = len(text),
      sync  = None)

  return text, affected_byte_range


# EOF
