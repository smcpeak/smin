E-P is slower because removing the line markers changes the token tree. The markers aren't noise: they decide how coarse MA3's units are. With them, the tree is coarser, MA3 needs fewer tests per pass, and it finishes in 4 passes instead of 7.

**What the markers do to the tree.** Inside `namespace std { ... }`, declarations are indented two spaces, but every `# N "file"` marker is at column 0. The INDENTATION grouping pass makes a column-0 line the head of a group, with every more-indented line after it as the body, until the next column-0 line. So each marker swallows everything up to the next marker or the closing `}`. An INDENTATION group isn't a brace group, so the whole thing is one BGCT child. Take the `ios_base.h` namespace (the one with `enum _Ios_Fmtflags`):

| | BGCT children | largest children |
|---|---|---|
| E | 24 | two marker-headed chunks of 707 and 1617 tokens |
| E-P | 126 | mostly 1–32 tokens each |

**Why fine-grained children cost passes.** I split the TSV logs by pass and exploration depth, and tracked the largest necessary count (L_NEC) at each tree level:

| | passes | tests | largest L_NEC at level 1 (pass 2, 3, 4, …) |
|---|---|---|---|
| E | 4 | 1104 | 10, 10, 1 |
| E-P | 7 | 2763 | 19, 29, 39, 49, 59, 62 |

In E, no namespace body ever has more than about 10 necessary children, because the markers have folded most of the body into a few big chunks. In E-P, one namespace body ends up with about 62 necessary children. With `NECESSITY_INCREMENT=10` it keeps hitting the limit, and that alone forces passes 5, 6 and 7. Every pass also resets necessity, so each of those passes re-tests every necessary child at every level it explores. That is where the extra 2.5 minutes goes. Passes 5–7 in E-P accept very little: about 9 kB removed over about 870 tests.

**A second effect inflates the necessary counts.** With paragraphs disabled, a multi-line declaration splits into one BGCT child per line, for example:

```
[[__nodiscard__]] constexpr        <- 6 tokens
inline _Ios_Fmtflags               <- 2 tokens
operator&(...) noexcept { ... }    <- 32 tokens
```

Removing just one of those lines gives a syntax error. So after a rejection drops G back to 1, each line gets marked necessary one test at a time, and every such function adds about 3 to L_NEC. Only a G≥3 batch that happens to cover exactly the whole declaration removes it. In E, many of these declarations sit inside marker chunks, where they aren't BGCT nodes at all.

**The markers are structure, not noise.** clang emits a marker at every `#include` entry and exit, and wherever it skips more than about 8 lines, such as the long Doxygen comments in libstdc++. So the markers line up with file and declaration boundaries, which is why removing them changes how MA3 performs. `-grepv` behaves like `-P` because the effect comes from the marker lines themselves, not from `-P`.

**Why E-P's output is bigger.** This part I'm less sure of. Access labels create the same kind of indivisible chunk: in the E-P result, `public:` in `basic_ios` heads a 163-token INDENTATION group with no BGCT children. E happened to empty `basic_ios` and `basic_ostream` far more, partly because markers inside those classes broke the chunks up differently. I haven't traced that down fully.

**Possible directions:**
- Group a whole declaration (lines up to its terminating `;` or `}`) into one node even with paragraphs off. This targets the false necessity from removing single lines.
- Decide whether a column-0 line inside a brace group should be allowed to head an INDENTATION group. Markers, `#pragma` lines and the `namespace __cxx11 {` line in `iosfwd` all trigger it now. The E data suggests the coarseness helps speed, but it creates large chunks MA3 can't break up.
- Raise `--ma3-necessity-increment` for inputs like this; that's the quick lever on the pass count.

I didn't change any code. The analysis scripts are in `/tmp/claude-1000/-home-scott-wrk-smin/49bf68d2-5d07-49b8-82c5-80ba709d3a05/scratchpad/`.
