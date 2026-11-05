smin: Structural Minimizer
==========================


Introduction
------------

This project implements a tool, `smin`, that automatically minimizes a
given input with respect to a given "acceptance test".  For example, it
can minimize a C++ program that crashes a compiler.  However, it does
not "parse" the input in a traditional sense, instead relying on various
heuristics to determine the input's hierarchical structure.

For more details, see:

  - smin-requirements.txt
  - structure-deduction-algorithm.txt
  - minimization-algorithm.txt

There are numerous other tools that do similar things.  The primary
novelies here are:

  - exploiting structure without a traditional parser
  - faster coarse minimization (fewer tested candidates to get to a
    moderately small input)
  - emphasis on minimizing C++ preprocessed translation units (while
    still being effective for other kinds of files)

See doc/related-work.txt (work in progress) for more comparison details.


AI Disclosure
-------------

Much of the code and tests in this repository were written with AI
assistance, under close human supervision.  All checkins that contain AI
generated material explain the division of labor in the git commit
message, including attribution to the particular AI system(s) used.  All
commits are made directly by a human, and that person takes full
responsibility for all committed content, regardless of the level of AI
involvement, to the same degree as if there was no AI involvement.

Any prose that includes AI-generated text is disclosed as such at the
top of the file (in addition to provenance in git commit messages).
Currently, that only applies to doc/related-work.txt.


LICENSE
-------

Copyright 2026 Scott McPeak

https://opensource.org/license/bsd-2-clause


EOF
