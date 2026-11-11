# minimizer.py
"""
Minimizer algorithm class.

See minimization-algorithm.txt.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from abstract_range import AbstractRange
from acceptance_test_result import AcceptanceTestResult
from byte_range import ByteRange
from minimizer_options import MinimizerOptions
from smin_token import SMToken
from start_report import TestStartReport
from token_tree import TokenTree, TTNode
from whitespace import (
  contains_newline,
  leading_whitespace,
  trail_indent,
)


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

  # The field names here are not the usual plain "start" and "stop"
  # because their semantics are a bit more complicated than with most
  # range classes.

  # Byte offset in the rendered candidate at the point we begin
  # rendering the first token in the affected token range.  The rendered
  # candidate before `abr_start` is the same as that of the last
  # accepted input.
  abr_start: int

  # Byte offset in the rendered candidate where the first live token
  # after the affected token range has its first non-whitespace
  # character; or None if there is no such token.  The rendered
  # candidate after `abr_stop` is the same as that of the last accepted
  # input.  (The candidate does not necessarily sync up at the end of
  # the affected tokens, since the whitespace that precedes the next
  # live token depends on the preceding gap.)
  abr_stop: Optional[int]


class Minimizer(ABC):
  """
  Minimize a token tree w.r.t. a given acceptance test.

  This is an abstract class.  Concrete subclasses provide the core of
  the minimization procedure, specifically, which nodes to try removing
  and in what order.  They are implemented in modules with names
  starting with "ma_".

  This superclass provides the common infrastructure, the most important
  parts of which are (1) holding the state about which parts of the tree
  have been replaced (`cur_replacement`), and (2) rendering a candidate
  input based on that information and the candidate tree replacements.
  """

  # ---- Input ----
  # Minimizer control options, the most important of which is the
  # acceptance test function.
  options: MinimizerOptions

  # The token tree representing the original input.  The algorithms
  # operate on `tree.root`.  `tree.eof_ws`, if present, is never
  # minimized, and only appears when rendering candidates.
  tree: TokenTree

  # ---- Fixed data derived from the input ----
  # The tokens of the original input under `tree.root`, in order.
  # Tokens are identified by their index in this list.  This excludes
  # `tree.eof_ws`.
  tokens: list[SMToken]

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
  #
  # This is incremented in _try_candidate and read in _make_report.
  sequence_num: int

  # Index of the current pass, i.e., outer loop iteration, starting at
  # 0.  Exactly what happens during a "pass" depends on the specific
  # algorithm in use.  This field's value is included in the progress
  # reports, and some algorithms use it internally as well.
  pass_index: int

  # ---- Output data ----
  # True if minimization stopped early because `options.should_stop`
  # returned True.
  stop_requested: bool


  def __init__(
    self,
    options: MinimizerOptions,
    tree: TokenTree,
  ) -> None:
    """
    Prepare to minimize the input represented by `tree`.

    Requires that the acceptance test has already accepted that input.
    """

    self.options = options
    self._set_tree(tree)


  def _set_tree(self, tree: TokenTree) -> None:
    """
    Set the tree to operate on, calculate the fixed data that depends on
    it, and reset the minimizer algorithm data.
    """
    self.tree = tree

    self.tokens = list(tree.root.tokens())
    self.node_span = {}
    end = self._compute_spans(tree.root, 0)
    assert end == len(self.tokens)

    self.cur_replacement = {}
    self.token_live = [True] * len(self.tokens)
    self.live_tok_count = len(self.tokens)
    self.minimizer_invoked = False

    self.sequence_num = 0
    self.pass_index = 0

    self.stop_requested = False

    initial_text = self.render_candidate({})
    self.accepted_size = len(initial_text)
    self.memoized_accept = {
      _digest(initial_text): AcceptanceTestResult.ACCEPT,
    }


  @abstractmethod
  def _preliminary_num_passes(self) -> int:
    """
    Return the total number of passes that would run if
    `self.options.max_passes` was None.
    """
    pass


  def _total_num_passes(self) -> int:
    """
    Return the total number of passes to run, taking
    `self.options.max_passes` into account.

    This is used for the progress reports.  Specific algorithms might
    also use it to control their outer loop.
    """
    ret: int = self._preliminary_num_passes()

    if self.options.max_passes is not None:
      ret = min(ret, self.options.max_passes)

    return ret


  def run_minimizer(self) -> AcceptanceTestResult:
    """
    Run the main minimizer algorithm.

    Requires that `run_minimizer` has not been invoked previously.

    It returns ACCEPT if we reached the end of the algorithm normally,
    or stopped early because `options.should_stop` returned True (in
    which case `stop_requested` is set), and INTERRUPTED otherwise.
    """

    assert not self.minimizer_invoked
    self.minimizer_invoked = True

    try:
      self._run_specific_minimizer()
    except _StopMinimization as e:
      return e.result

    return AcceptanceTestResult.ACCEPT


  @abstractmethod
  def _run_specific_minimizer(self) -> None:
    """
    Run the particular minimizer algorithm specified by the user.
    """
    pass


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
    self._fill_ctm(self.tree.root, {}, ctm)
    return ctm.count(None)


  def render_candidate(self, extra: dict[int, bytes]) -> bytes:
    """
    Render the input with the current replacements, plus those in
    `extra`, which maps a node's id() to its candidate replacement.
    The result ends with `tree.eof_ws`, if any.
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
      self._fill_ctm(self.tree.root, extra, ctm))

    # Render the candidate using the CTM.
    text: bytes
    affected_byte_range: Optional[_AffectedByteRange]
    text, affected_byte_range = (
      _render_ctm([t.text for t in self.tokens],
                  ctm,
                  affected_token_range))

    # Every candidate ends with the original EOF whitespace, if any, so
    # if the affected range extends to the end of the tokens, it stops
    # just before that whitespace.
    if (affected_byte_range is not None and
        affected_byte_range.abr_stop is None):
      affected_byte_range.abr_stop = len(text)
    if self.tree.eof_ws is not None:
      text += self.tree.eof_ws.text

    if affected_byte_range is None:
      return text, None

    # The candidate and the last accepted input agree after `abr_stop`,
    # so the end of the modified range is that far from the end of the
    # latter.
    assert affected_byte_range.abr_stop is not None
    stop: int = (
      self.accepted_size - (len(text) - affected_byte_range.abr_stop))
    return text, ByteRange(affected_byte_range.abr_start, stop)


  def node_size(self, node: TTNode) -> int:
    """Return the number of live tokens in `node`."""
    span = self.node_span[id(node)]
    return sum(self.token_live[span.start : span.stop])


  def _get_surviving_nondelim_children(
    self,
    node: TTNode,
  ) -> list[TTNode]:
    """
    Return the children of `node` that are not replaced, excluding the
    delimiters if `node` is a delimiter group.
    """

    all_children: list[TTNode] = node.children

    # Range of non-delimiter children.
    lo, hi = ((1, len(all_children)-1) if node.is_delim_group()
              else (0, len(all_children)))

    # Filter the range for having not been replaced.
    return [
      c
      for c in all_children[lo:hi]
      if id(c) not in self.cur_replacement
    ]


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
    self.options.acceptance.report_test_starting(report)

    result: Optional[AcceptanceTestResult] = self.memoized_accept.get(digest)
    if result is not None:
      self.options.acceptance.report_test_finished(result, True)
    else:
      result = self.options.acceptance.test_acceptance(text, report)
      self.options.acceptance.report_test_finished(result, False)
      if result == AcceptanceTestResult.INTERRUPTED:
        raise _StopMinimization(result)
      self.memoized_accept[digest] = result

    accepted: bool = result == AcceptanceTestResult.ACCEPT
    if accepted:
      self.accepted_size = len(text)
      self._commit(extra)

    # This is checked after committing so that, if we stop, the most
    # recently accepted input includes this candidate when accepted.
    if (self.options.should_stop is not None and
        self.options.should_stop()):
      self.stop_requested = True
      raise _StopMinimization(AcceptanceTestResult.ACCEPT)

    return accepted


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

    return TestStartReport(
      sequence_num=self.sequence_num,
      last_accepted_tok_count=self.live_tok_count,
      pass_num=self.pass_index + 1,
      total_num_passes=self._total_num_passes(),
      granularity=self._get_cur_granularity(),
      completion_fraction=self._get_cur_completion_fraction(nodes),
      removed_tok_count=sum(self.node_size(n) for n in nodes),
      initial_tok_count=len(self.tokens),
      changed_byte_range=changed,
    )


  @abstractmethod
  def _get_cur_granularity(self) -> float:
    """
    Return the current algorithm granularity for inclusion in the
    progress report for the acceptance test we are about to perform.
    The exact meaning depends on which algorithm is in use.
    """
    pass


  def _get_cur_completion_fraction(self, nodes: list[TTNode]) -> float:
    """
    Return the fraction of the current pass that has been completed,
    for inclusion in the progress report for the test of the candidate
    replacing `nodes`.

    By default, this is based on the position of the candidate within
    the file, for an algorithm that works from its end to its start.
    """

    # `e` (called "E" in the spec) is the 1-based index, among the live
    # tokens, of the last live token in the candidate, or of the live
    # token to its left if it has none.  Either way, it is the number of
    # live tokens before the end of the rightmost node.
    end = max(self.node_span[id(n)].stop for n in nodes)
    e = sum(self.token_live[:end])

    num_live = self.live_tok_count

    return (num_live - e) / num_live


class _StopMinimization(Exception):
  """Raised to unwind the recursion when minimization stops early."""

  def __init__(self, result: AcceptanceTestResult) -> None:
    super().__init__(result.name)
    self.result = result


def _digest(data: bytes) -> bytes:
  """Return the MD5 digest of `data`."""
  return hashlib.md5(data, usedforsecurity=False).digest()


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

  # Rendered candidate as a sequence of token texts.  Like the tokens in
  # the token tree, the token texts here may have leading whitespace.
  candidate: list[bytes] = []

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
      # what has been rendered so far to `candidate`.
      affected_byte_range = _AffectedByteRange(
        abr_start = sum(map(len, candidate)),
        abr_stop  = None)

    if replacement is None:
      if not in_gap:
        candidate.append(text)

      else:
        # This is B, the end of the last piece of the gap.
        ws = leading_whitespace(text)
        indent = trail_indent(b"".join(trivial))
        if contains_newline(ws):
          candidate.append(text)
        elif indent:
          candidate.append(indent + text[len(ws):])
        elif not ws and seen_live:
          candidate.append(b" " + text)
        else:
          candidate.append(text)
        trivial = []
        in_gap = False

      seen_live = True

      if (affected_token_range is not None and
          i >= affected_token_range.stop):
        # We should have already created the ABR.
        assert affected_byte_range is not None

        if affected_byte_range.abr_stop is None:
          # Current `candidate` length.
          candidate_len_bytes: int = sum(map(len, candidate))

          # Length of after-first-whitespace byte sequence that was just
          # added for the current token.
          len_after_ws: int = len(text) - len(leading_whitespace(text))

          # Only the whitespace emitted before this token's own
          # non-whitespace text can differ from the last accepted input.
          affected_byte_range.abr_stop = candidate_len_bytes - len_after_ws

    else:
      in_gap = True
      if replacement:
        # End of a piece with a non-trivial replacement.
        candidate.append(
          trail_indent(b"".join(trivial) + leading_whitespace(text)) +
          replacement)
        trivial = []
      else:
        trivial.append(text)

  # Any trivially replaced tokens at the end are discarded.
  text = b"".join(candidate)

  if affected_token_range is None:
    return text, None

  # In the current code, I believe this cannot fail.  We would need to
  # have been given an empty token range that starts at the end of the
  # file, but _fill_ctm gets the seed token ranges from `node_span`,
  # which describes the original tree, which (due to how it is built)
  # never has nodes that do not contain any tokens.
  #
  # See doc/affected-byte-range-assertion.txt for even more analysis.
  #
  # Fow now I'll hold off on strengthening assertions elsewhere since
  # this isn't particularly important, other than for checking my
  # understanding of how the code in this function operates.
  assert affected_byte_range is not None

  # The "impossible" condition isn't difficult to handle if necessary.
  if affected_byte_range is None:
    # We never crossed into the affected range, so return an effectively
    # empty byte range.
    affected_byte_range = _AffectedByteRange(
      abr_start = len(text),
      abr_stop  = None)

  return text, affected_byte_range


# EOF
