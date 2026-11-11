This file has Claude's analysis of a minimizer performance issue.

Claude took about 7 minutes to do its analysis and writeup.  I then
asked it to write that to a file (this file), and I then added the
prompt and reformatted the answer for easier reading as text.  I also
added my own summary to the end.

Claude's text points to a /tmp directory at the end.  I haven't
preserved its contents.  (I looked at it briefly.  Nothing jumped out as
being worth saving.)


Prompt
------

I'd like help with diagnosing something about the behavior of MA3:

* When I run "./run_bm.py smin-ma3 hello-cpp-E" in the `bm` directory,
  it takes just over 2 minutes to run, and produces minimized output
  with 2491 tokens, about 15 kB, and 840 lines.  This is significantly
  faster than previous algorithms, and while the output is a bit larger,
  that is fine for a coarse minimizer; so far so good.

* However, when I run "./run_bm.py smin-ma3 hello-cpp-E-P" in the same
  directory, it takes about 4.5 minutes, and produces minimized output
  that has 3705 tokens, about 21 kB, and 819 lines.  The output size is
  still within the range of acceptibility, but it takes more than twice
  as long.

This difference in run time is somewhat mysterious because the only
difference in the input is that hello-cpp-E-P adds the -P preprocessing
option (in gen.sh), which causes line markers to not be emitted, and
line markers are (I think!) basically uncorrelated with the structure of
the input, and hence ought to be noise.  Yet the version that *has* them
(hello-cpp-E) performs much better.

I've seen similar behavior (with hello-cpp-E and hello-cpp-E-P) using
the other minimization algorithms, so I don't think this is simply a
fluke due to "lucky" or "unlucky" placement of early partition
boundaries, although I haven't ruled that out.

I also tried hello-cpp-E-grepv, which removes line markers using `grep`
instead of -P, and the behavior is similar to when using -P.

So: see if you can figure out why MA3 on hello-cpp-E is faster than MA3
on hello-cpp-E-P despite the latter being smaller and (seemingly)
simpler.

The "bm/out" directory contains the results of previous runs.  You can
look at them if doing so is helpful.  There's no need to preserve them;
I can easily re-run the benchmarks.


Answer
------

E-P is slower because removing the line markers changes the token tree.
The markers aren't noise: they decide how coarse MA3's units are. With
them, the tree is coarser, MA3 needs fewer tests per pass, and it
finishes in 4 passes instead of 7.

**What the markers do to the tree.**

Inside `namespace std { ... }`, declarations are indented two spaces,
but every `# N "file"` marker is at column 0. The INDENTATION grouping
pass makes a column-0 line the head of a group, with every more-indented
line after it as the body, until the next column-0 line. So each marker
swallows everything up to the next marker or the closing `}`. An
INDENTATION group isn't a brace group, so the whole thing is one BGCT
child. Take the `ios_base.h` namespace (the one with `enum
_Ios_Fmtflags`):

|     | BGCT children | largest children                                |
|-----|---------------|-------------------------------------------------|
| E   |            24 | two marker-headed chunks of 707 and 1617 tokens |
| E-P |           126 | mostly 1--32 tokens each                        |

**Why fine-grained children cost passes.**

I split the TSV logs by pass and exploration depth, and tracked the
largest necessary count (L_NEC) at each tree level:

|     | passes | tests | largest L_NEC at level 1 (pass 2, 3, 4, ...) |
|-----|--------|-------|----------------------------------------------|
| E   |      4 |  1104 | 10, 10, 1                                    |
| E-P |      7 |  2763 | 19, 29, 39, 49, 59, 62                       |

In E, no namespace body ever has more than about 10 necessary children,
because the markers have folded most of the body into a few big chunks.
In E-P, one namespace body ends up with about 62 necessary children.
With `NECESSITY_INCREMENT=10` it keeps hitting the limit, and that alone
forces passes 5, 6 and 7. Every pass also resets necessity, so each of
those passes re-tests every necessary child at every level it explores.
That is where the extra 2.5 minutes goes. Passes 5--7 in E-P accept
very little: about 9 kB removed over about 870 tests.

**A second effect inflates the necessary counts.**

With paragraphs disabled, a multi-line declaration splits into one BGCT
child per line, for example:

```
[[__nodiscard__]] constexpr        <- 6 tokens
inline _Ios_Fmtflags               <- 2 tokens
operator&(...) noexcept { ... }    <- 32 tokens
```

Removing just one of those lines gives a syntax error. So after a
rejection drops G back to 1, each line gets marked necessary one test at
a time, and every such function adds about 3 to L_NEC. Only a G≥3
batch that happens to cover exactly the whole declaration removes it. In
E, many of these declarations sit inside marker chunks, where they
aren't BGCT nodes at all.

**The markers are structure, not noise.**

clang emits a marker at every `#include` entry and exit, and wherever it
skips more than about 8 lines, such as the long Doxygen comments in
libstdc++. So the markers line up with file and declaration boundaries,
which is why removing them changes how MA3 performs. `-grepv` behaves
like `-P` because the effect comes from the marker lines themselves, not
from `-P`.

**Why E-P's output is bigger.**

This part I'm less sure of. Access labels create the same kind of
indivisible chunk: in the E-P result, `public:` in `basic_ios` heads a
163-token INDENTATION group with no BGCT children. E happened to empty
`basic_ios` and `basic_ostream` far more, partly because markers inside
those classes broke the chunks up differently. I haven't traced that
down fully.

**Possible directions:**

- Group a whole declaration (lines up to its terminating `;` or `}`)
  into one node even with paragraphs off. This targets the false
  necessity from removing single lines.

- Decide whether a column-0 line inside a brace group should be allowed
  to head an INDENTATION group. Markers, `#pragma` lines and the
  `namespace __cxx11 {` line in `iosfwd` all trigger it now. The E data
  suggests the coarseness helps speed, but it creates large chunks MA3
  can't break up.

- Raise `--ma3-necessity-increment` for inputs like this; that's the
  quick lever on the pass count.

I didn't change any code. The analysis scripts are in
`/tmp/claude-1000/-home-scott-wrk-smin/49bf68d2-5d07-49b8-82c5-80ba709d3a05/scratchpad/`.


My summary
----------

Key points from Claude's analysis:

* Line markers interact with indentation grouping to cause nodes to have
  fewer children overall.  Evidently, keeping a smaller number of larger
  children tends to work better, even when that means they have some
  unnecessary text inside them.

* Larger children also avoids a problem where, without paragraphs, I
  split multi-line declarations badly and waste a lot of time trying to
  take them apart in syntactically inappropriate ways.

* With E-P, the necessity limit is too small, so we waste time retrying
  a bunch of nodes and expanding that limit.  In fact, Claude basically
  ascribes the entire extra 2.5 minutes to retries while expanding
  necessity.

* Meanwhile, indentation causes E-P to sometimes very coarsely divide
  classes due to "public:", etc., whereas the line markers cause
  divisions to appear.

Summarizing my summary, indentation grouping with line markers produces
groups that have surprisingly useful structure.

Consequently, if I want the algorithms to perform well without line
markers (and of course I do), then I need ways to recover at least as
much structure as the line markers were (accidentally!) providing.


EOF
