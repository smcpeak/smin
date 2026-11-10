# ma_ma3.py
"""
Minimization algorithm 3 (MA3).

See minimization-algorithm.txt, sections "Brace Group Child Tree
(BGCT)", "Minimization Algorithm 3 (MA3)", and "MA3 Progress
Reporting".
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field
from typing import Optional

from byte_range import ByteRange
from min_alg_kind import MinimizerAlgorithmKind
from min_alg_selector import MinimizerAlgorithmSelector
from minimizer import Minimizer
from minimizer_options import MinimizerOptions
from start_report import MA3RecMinAR, MA3ReportData, TestStartReport
from token_tree import TokenTree, TTNode


@dataclass(frozen=True, kw_only=True)
class MA3MinimizerSelector(MinimizerAlgorithmSelector):
  """
  Select the MA3 algorithm and control its parameters.
  """

  # NECESSITY_INCREMENT: The amount by which `max_necessity` increases
  # with each outer loop iteration.
  necessity_increment: int = 10

  # MAX_EXPLORATION_DEPTH: The maximum value of `exploration_depth`.
  max_exploration_depth: int = 4


  def __post_init__(self) -> None:
    assert self.necessity_increment >= 1
    assert self.max_exploration_depth >= 1


  def alg_kind(self) -> MinimizerAlgorithmKind:
    return MinimizerAlgorithmKind.MA3


@dataclass(eq=False)
class BGCTNode:
  """
  A node in the brace group child tree (BGCT).

  See the spec for more details, but the essential idea of the BGCT is
  it is an ordered embedded subtree formed from the token tree by
  keeping only the direct children of brace-delimited group nodes (plus
  the root and its children).

  The MA3 algorithm then operates primarily on this reduced structure,
  motivated by the observation that it contains, in some sense, the most
  important hierarchical structure.

  Equality is identity, since each one corresponds to a distinct node
  in the token tree.
  """

  # The token tree node this corresponds to.
  ttnode: TTNode

  # Number of edges from the BGCT root to this node.
  level: int

  # The token tree nodes on the path from just below the BGCT parent of
  # this node, down to and including `ttnode`.  Empty for the root.
  #
  # This is used to check liveness (if any node on the path is replaced,
  # then this node is not live), and to compute RCPBG.
  path: list[TTNode] = field(default_factory=list)

  # All children in the BGCT, including those that have since been
  # replaced, in left-to-right order.
  all_children: list[BGCTNode] = field(default_factory=list)

  # Length of necessary(N), which is always a suffix of the live
  # children.
  #
  # Nodes beyond this "divider" have been determined to be "necessary"
  # for a candidate to be accepted, and hence their replacement will not
  # be re-tried, although that determination is reset at the start of
  # each outer loop iteration.
  num_necessary: int = 0


class MA3Minimizer(Minimizer):
  """
  MA3 works on the brace group child tree, trying to remove nodes near
  the end of the file first, with effort per node limited by a
  "necessity" limit and an iteratively deepening exploration depth,
  both of which grow to keep making progress.

  See minimization-algorithm.txt for details.
  """

  # ---- Fixed data ----
  # Algorithm-specific options.
  ma3_selector: MA3MinimizerSelector

  # The root of the BGCT.
  bgct_root: BGCTNode

  # All BGCT nodes, in preorder.
  #
  # The primary use for this is to reset `BGCTNode.num_necessary`.  It
  # is also used at the start to compute `preliminary_num_passes`.
  bgct_nodes: list[BGCTNode]

  # Pm (max pass count) before applying `max_passes`.
  preliminary_num_passes: int

  # ---- Algorithm state ----
  # The maximum number of "necessary" nodes to accumulate within any
  # given BGCT node.
  max_necessity: int = 0

  # The maximum level of BGCT nodes to examine and consider replacing.
  exploration_depth: int = 0

  # ---- Progress data ----
  # For each active `_min_subtree` call that is in its loop over the
  # necessary children, outermost first, the [C, N] values: the index of
  # the child being explored within `reverse(necessary(N))`, and the
  # length of that list.
  activation_records: list[MA3RecMinAR]

  # LVL, L_NEC, and G from the current `_min_node` call.
  cur_level: int = 0
  cur_level_necessary: int = 0
  cur_granularity: int = 0


  def __init__(
    self,
    options: MinimizerOptions,
    tree: TokenTree,
  ) -> None:
    assert options.alg_kind() == MinimizerAlgorithmKind.MA3
    assert isinstance(options.selector, MA3MinimizerSelector)
    super().__init__(options, tree)

    self.ma3_selector = options.selector
    self.activation_records = []

    self.bgct_nodes = []
    self.bgct_root = self._build_bgct()

    # The maximum number of outer loop iterations is dictated by the
    # maximum number of BGCT children in any node, divided by the
    # necessity increment.
    #
    # It is defensively forced to be at least 1 because the outer loop
    # is always entered, but (I think) if that lower bound ever has any
    # effect here, then the tree is effectively empty, and no progress
    # report will be issued, so it ultimately doesn't matter.
    #
    self.preliminary_num_passes = max(1, max(
      (math.ceil(len(n.all_children) / self._necessity_increment())
       for n in self.bgct_nodes
       if n.level < self._max_exploration_depth()),
      default=0))


  def _necessity_increment(self) -> int:
    return self.ma3_selector.necessity_increment

  def _max_exploration_depth(self) -> int:
    return self.ma3_selector.max_exploration_depth


  # ---- BGCT ----
  def _build_bgct(self) -> BGCTNode:
    """
    Build the BGCT for `tree`, populating `bgct_nodes`, and return its
    root.
    """
    root = BGCTNode(self.tree.root, 0)
    self.bgct_nodes.append(root)
    self._add_bgct_children(root, root.ttnode, [])
    return root


  def _add_bgct_children(
    self,
    parent: BGCTNode,
    ttnode: TTNode,
    path: list[TTNode],
  ) -> None:
    """
    Search the token tree below `ttnode`, which is either
    `parent.ttnode` or a descendant of it (reached via `path`, excluding
    `parent.ttnode`) with no BGCT node in between, and add the BGCT
    nodes found to `parent`, recursively building their subtrees.
    """
    assert ((len(path) == 0 and ttnode == parent.ttnode) or
            (len(path) != 0 and ttnode != parent.ttnode and
                                ttnode == path[-1]))

    is_root: bool = ttnode is self.tree.root
    is_bg: bool = self.options.language.is_brace_group(ttnode)
    children: list[TTNode] = ttnode.children

    for i, c in enumerate(children):
      c_path = path + [c]
      if is_root or (is_bg and 0 < i < len(children)-1):
        # `c` is a BGCT child of `parent`, either because it is a child
        # of the root, or it is a child of a brace group, but not either
        # of the delimiter tokens.
        node = BGCTNode(c, parent.level + 1, c_path)
        parent.all_children.append(node)
        self.bgct_nodes.append(node)
        self._add_bgct_children(node, c, [])
      else:
        # Keep looking below `c`.
        self._add_bgct_children(parent, c, c_path)


  def _is_live_child(self, node: BGCTNode) -> bool:
    """
    True if `node`, the child of some live BGCT node, is not replaced
    and has no replaced ancestor.
    """
    return not any(id(n) in self.cur_replacement for n in node.path)


  def children(self, node: BGCTNode) -> list[BGCTNode]:
    """children(N) in the spec: the live children of live `node`."""
    return [c for c in node.all_children if self._is_live_child(c)]


  def necessary(self, node: BGCTNode) -> list[BGCTNode]:
    """necessary(N) in the spec, in left-to-right order."""
    live = self.children(node)
    return live[len(live) - node.num_necessary : ]


  def rcpbg(self, node: BGCTNode) -> Optional[TTNode]:
    """
    Return the token tree parent of the rightmost live child of non-root
    `node`, if that is a brace group, or None if there is no such group.

    The idea here is if `node` is something like a C++ function or class
    definition, or a control flow statement like `if`, then the RCPBG is
    the brace-enclosed "body", which might be profitably replaced by a
    semicolon.  (Other minimization algorithms do this naturally by
    operating on the token tree, but because MA3 operates the BGCT, it
    would otherwise miss these replacements.)
    """

    if node is self.bgct_root:
      return None

    live = self.children(node)
    if not live:
      return None

    rightmost_child: BGCTNode = live[-1]

    # Path in the token tree from `node` to its rightmost child in the
    # BGCT.
    path: list[TTNode] = rightmost_child.path
    assert path[-1] == rightmost_child.ttnode

    # The path of a child begins just below its BGCT parent, so the
    # element before the child is its token tree parent, unless the
    # path has just one element, in which case the parent is `node`.
    tt_parent: TTNode = path[-2] if len(path) >= 2 else node.ttnode

    if self.options.language.is_brace_group(tt_parent):
      return tt_parent
    return None


  # ---- Algorithm ----
  def _preliminary_num_passes(self) -> int:
    return self.preliminary_num_passes


  def _run_specific_minimizer(self) -> None:
    """
    Minimize the entire tree, with attention focused on the end of the
    file, attempting to remove nodes in layers, but with gradually
    increasing limits on effort spent per node and how far we search
    from the end.

    Implements spec function `ma3_min_tree`.
    """

    self.max_necessity = 0
    pass_count: int = 0

    while True:
      # Bump the pass count, and stop if --max-passes says to.
      pass_count += 1
      if (self.options.max_passes is not None and
          pass_count > self.options.max_passes):
        break
      self.pass_index = pass_count - 1

      # Expand scope, re-try previously rejected replacements.
      self.max_necessity += self._necessity_increment()
      for n in self.bgct_nodes:
        n.num_necessary = 0

      # Iteratively deepen the candidates for replacement.
      hit_limit: bool = False
      for ed in range(1, self._max_exploration_depth() + 1):
        self.exploration_depth = ed

        # Remove what we can, subject to `max_necessity`, down to
        # `exploration_depth`.
        if self._min_subtree(self.bgct_root):
          hit_limit = True

      # Stop when the necessity limit is not stopping us at any level.
      if not hit_limit:
        break


  def _min_subtree(self, node: BGCTNode) -> bool:
    """
    `ma3_min_subtree` in the spec: Minimize `node`, then its necessary
    children, recursively, down to the exploration depth.  Return True
    if any node hit the necessity limit.
    """

    # Minimize `node` itself.  `ret` tracks if any call hit the
    # necessity limit.
    ret: bool = self._min_node(node)

    # The children of `node` are at level `node.level+1`.  And the
    # recursive call first tries removing `c`'s children (the
    # grandchildren of `node`).  So, only recurse if the grandchildren's
    # level is within the allowed exploration depth.
    if node.level + 2 <= self.exploration_depth:

      # This list (of live, necessary children) does not change during
      # the loop, since the recursive calls only replace nodes within
      # the children's subtrees.
      rev_nec: list[BGCTNode] = list(reversed(self.necessary(node)))

      # Add a record of this recursive call.
      frame = MA3RecMinAR(0, len(rev_nec))
      self.activation_records.append(frame)

      try:
        # Try to minimize each of the necessary children individually.
        for i, c in enumerate(rev_nec):
          frame.child_index = i
          if self._min_subtree(c):
            ret = True

      finally:
        self.activation_records.pop()

    return ret


  def _min_node(self, node: BGCTNode) -> bool:
    """
    `ma3_min_node` in the spec: Try to replace the non-necessary
    children of `node`, from last to first, without recursion.  Return
    True if we stopped due to hitting the necessity limit.
    """

    # Number of children to try removing at once.
    g: int = 1

    while True:
      # Stop if all of the children are necessary.
      live: list[BGCTNode] = self.children(node)
      assert not (node.num_necessary > len(live))
      if node.num_necessary == len(live):
        return False

      # Also stop if we hit the limit.
      if node.num_necessary >= self.max_necessity:
        return True

      # The children that have not been determined to be necessary.
      non_nec = live[ : len(live) - node.num_necessary]

      # The last `g` of them; we will try to replace them.
      assert 1 <= g <= len(non_nec)
      cc = non_nec[len(non_nec) - g : ]

      # Number of non-replaced, non-necessary children that will remain
      # if we replace all of them in `cc`.
      remaining = len(non_nec) - len(cc)

      # Update the progress report data before running `_try_candidate`.
      self.cur_level = node.level
      self.cur_level_necessary = node.num_necessary
      self.cur_granularity = g

      if len(cc) > 1:
        # We are attempting to replace multiple nodes, so only attempt
        # the trivial replacement.
        tt_nodes: list[TTNode] = [c.ttnode for c in cc]

        # TODO: Factor the several places that use `_try_candidate` and
        # supply a dict with trivial replacements.
        if self._try_candidate({id(n): b"" for n in tt_nodes}, tt_nodes):
          # ACCEPT: Double `g`, up to the number remaining, to
          # optimistically accelerate further removal.
          g = min(2 * g, remaining)

        else:
          # REJECT: Halve `g`, doing a sort of binary search to zoom in
          # on the next (going in reverse order) element of `cc` that is
          # necessary.
          g = len(cc) // 2

        continue

      # We are attempting to remove just one node, `c`.
      c: BGCTNode = cc[0]
      if self._try_candidate({id(c.ttnode): b""}, [c.ttnode]):
        # ACCEPT trivial replacement.
        g = min(2 * g, remaining)
        continue

      # Non-trivial replacement?
      replacement: Optional[bytes] = (
        self.options.language.non_trivial_replacement(c.ttnode))
      if (replacement and
          self._try_candidate({id(c.ttnode): replacement},
                              [c.ttnode])):
        # ACCEPT non-trivial replacement.  Since it was non-trivial, and
        # thus required attention to the individual node, we
        # optimistically expect the same to be true of the next node, so
        # do not increase `g`.
        g = min(g, remaining)
        continue

      # Try the non-trivial replacement of the brace group containing
      # the children of `c`.  Skip it if that group is `c` itself, as
      # the candidate would be the same as the one just tried.
      bg = self.rcpbg(c)
      if bg is not None and bg is not c.ttnode:
        replacement = self.options.language.non_trivial_replacement(bg)
        if replacement and self._try_candidate({id(bg): replacement},
                                               [bg]):
          # `c` itself survives, and is now necessary.
          node.num_necessary += 1

          # ACCEPT non-trivial replacement of a "body".
          g = min(g, remaining)
          continue

      # REJECT ONE: `c` is necessary.
      node.num_necessary += 1

    # Not reached.


  # ---- Progress reporting ----
  def _get_cur_granularity(self) -> float:
    return float(self.cur_granularity)


  def _get_cur_completion_fraction(self, nodes: list[TTNode]) -> float:
    """F: the root necessity fraction."""
    n = len(self.children(self.bgct_root))
    if n == 0:
      return 1.0
    return self.bgct_root.num_necessary / n


  def _make_report(
    self,
    nodes: list[TTNode],
    changed: ByteRange,
  ) -> TestStartReport:
    return dataclasses.replace(
      super()._make_report(nodes, changed),
      ma3_data = MA3ReportData(
        max_necessity         = self.max_necessity,
        exploration_depth     = self.exploration_depth,
        max_exploration_depth = self._max_exploration_depth(),
        activation_records    = self.activation_records,
        level                 = self.cur_level,
        level_necessary       = self.cur_level_necessary,
        granularity           = self.cur_granularity,
      ))


# EOF
