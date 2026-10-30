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

from acceptance_test_result import AcceptanceTestResult
from smin_token import SMToken
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
# as "interesting" for minimization purposes.  In normal operation, this
# spawns a new process to run an external program, and waits for it to
# terminate.
AcceptanceTestFunc = Callable[[bytes], AcceptanceTestResult]


@dataclass(frozen=True)
class TestStartReport:
  """
  Details to report to the user when an acceptance test is starting.
  """

  # The short identifiers like "N" are the names used in the spec.

  # N: Numbering of the invocations during this minimization attempt,
  # starting with 1.
  sequence_num: int

  # S: Number of live tokens in the most recently accepted input.
  last_accepted_tok_count: int

  # P: Outer loop pass number, starting with 1, and ending with
  # `total_num_passes`.
  pass_num: int

  # Pm: The total number of passes we expect to perform.
  total_num_passes: int

  # G: Current granularity, in tokens.  The algorithm is (mainly) trying
  # to remove nodes of about this size.
  granularity: float

  # F: Estimate of how far we are through the current pass, in [0,1].
  completion_fraction: float

  # R: Number of live tokens that were removed to create the current
  # candidate.  That candidate's size (in tokens) can be calculated as
  # `last_accepted_tok_count - removed_tok_count`.
  removed_tok_count: int

  # Number of tokens in the initial input.  This is the maximum value of
  # S, G, and R, so it determines how wide their fields are.
  initial_tok_count: int


  def to_console_string(self) -> str:
    """
    Return the line to print to the console before the test starts,
    without a trailing newline.  See minimization-algorithm.txt,
    "Progress report".
    """

    # Width of a field holding up to `initial_tok_count`.
    tok_width = len(str(self.initial_tok_count))

    # The granularity is printed with one digit after the decimal point.
    g_width = tok_width + 2

    p_width = len(str(self.total_num_passes))

    # Truncate rather than round, so that a fraction just below 1 does
    # not print as 100.
    f_percent = min(int(self.completion_fraction * 100), 99)

    status = (
      f"P=({self.pass_num:0{p_width}d}/{self.total_num_passes}) "
      f"G={self.granularity:0{g_width}.1f} "
      f"F={f_percent:02d}% "
      f"R={self.removed_tok_count:0{tok_width}d}")

    return (
      f"N={self.sequence_num:06d} "
      f"S={self.last_accepted_tok_count:0{tok_width}d} "
      f"{status} ...")


# Signature of a function that accepts a test start report.  In normal
# operation, the callee prints this data to the console.
TestStartReportFunc = Callable[[TestStartReport], None]

# Signature of a function called when a test finishes.  Again, this is
# normally just printed to the console.
TestFinishedReportFunc = Callable[[AcceptanceTestResult], None]


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

  # Map from the id() of each node to the half-open range [start, end)
  # of indices in `tokens` of the tokens it contains.
  node_span: dict[int, tuple[int, int]]

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

  # Map from the 16-byte MD5 digest of a candidate input to its outcome,
  # for a candidate that has already been tested.  The INTERRUPTED
  # outcome is never stored here.
  memoized_accept: dict[bytes, AcceptanceTestResult]

  # Initially False, this is set to true by `run_minimizer`, and used to
  # check that that function is only invoked once.
  minimizer_invoked: bool

  # ---- Progress data ----
  # Number of acceptance test invocations so far.
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
  ) -> None:
    """
    Prepare to minimize the input represented by `tree_root`.

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

    self.cur_replacement = {}
    self.token_live = [True] * len(self.tokens)
    self.live_tok_count = len(self.tokens)
    self.minimizer_invoked = False

    self.sequence_num = 0

    # This is floor(log_2(S))+1 for S > 0, and 0 for S = 0.
    self.total_num_passes = len(self.tokens).bit_length()
    self.pass_index = 0

    self.memoized_accept = {
      _digest(self.render_candidate({})): AcceptanceTestResult.ACCEPT,
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


  # TODO: This needs a unit test.
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
    """

    # Candidate token map: for each token, None if it is live, and
    # otherwise its replacement text.
    ctm: list[bytes | None] = [None] * len(self.tokens)
    self._fill_ctm(self.tree_root, extra, ctm)
    return _render_ctm([t.text for t in self.tokens], ctm)


  def node_size(self, node: TTNode) -> int:
    """Return the number of live tokens in `node`."""
    start, end = self.node_span[id(node)]
    return sum(self.token_live[start:end])


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
    self.node_span[id(node)] = (start, end)
    return end


  def _fill_ctm(
    self,
    node: TTNode,
    extra: dict[int, bytes],
    ctm: list[bytes | None],
  ) -> None:
    """
    Record in `ctm` the replacements of `node` and its descendants.  A
    replacement on a node overrides any on its descendants.
    """
    replacement = extra.get(id(node))
    if replacement is None:
      replacement = self.cur_replacement.get(id(node))

    if replacement is not None:
      start, end = self.node_span[id(node)]
      if start < end:
        ctm[start] = replacement
        for i in range(start+1, end):
          ctm[i] = b""
    else:
      for child in node.children:
        self._fill_ctm(child, extra, ctm)


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
    text: bytes = self.render_candidate(extra)
    digest: bytes = _digest(text)

    result: Optional[AcceptanceTestResult] = self.memoized_accept.get(digest)
    if result is None:
      self.sequence_num += 1
      self.report_test_starting(self._make_report(nodes))
      result = self.test_acceptance(text)
      self.report_test_finished(result)
      if result == AcceptanceTestResult.INTERRUPTED:
        raise _StopMinimization(result)
      self.memoized_accept[digest] = result

    if result != AcceptanceTestResult.ACCEPT:
      return False

    self._commit(extra)
    return True


  def _commit(self, extra: dict[int, bytes]) -> None:
    """Make the replacements in `extra` current."""
    self.cur_replacement.update(extra)

    for key in extra:
      start, end = self.node_span[key]
      for i in range(start, end):
        if self.token_live[i]:
          self.token_live[i] = False
          self.live_tok_count -= 1

    if self.live_tok_count == 0:
      # Nothing is left to remove.
      raise _StopMinimization(AcceptanceTestResult.ACCEPT)


  def _make_report(self, nodes: list[TTNode]) -> TestStartReport:
    """Make the report for a test of the candidate replacing `nodes`."""

    # `e` (called "E" in the spec) is the 1-based index, among the live
    # tokens, of the last live token in the candidate, or of the live
    # token to its left if it has none.  Either way, it is the number of
    # live tokens before the end of the rightmost node.
    end = max(self.node_span[id(n)][1] for n in nodes)
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


def _render_ctm(texts: list[bytes], ctm: list[bytes | None]) -> bytes:
  """
  Render the candidate where token i has original text `texts[i]`, and
  is live if `ctm[i]` is None, and otherwise replaced by `ctm[i]`.

  See minimization-algorithm.txt, "Candidate rendering".
  """
  out: list[bytes] = []

  # True once a live token has been emitted, i.e., there is an "A".
  seen_live = False

  # True if there is a gap of dead tokens since the last live token (or
  # the start of the input).
  in_gap = False

  # Texts of the dead tokens with trivial replacements since the end of
  # the last piece.
  trivial: list[bytes] = []

  for text, replacement in zip(texts, ctm, strict=True):
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
  return b"".join(out)


# EOF
