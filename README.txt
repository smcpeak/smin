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


Module Naming Conventions
-------------------------

There are quite a few modules that pertain to concepts related to
minimization, and hence have similar names.  To clarify their purpose,
they are named according to this scheme:

* minimizer*.py: The core minimizer.

* min_alg*.py: Infrastructure for selecting and instantiating a specific
  algorithm.

* ma_*.py: The individual minimization algorithms.

For a module foo.py, its associated tests are in foo_test.py.
(Rationale: That keeps the module and its tests next to each other in an
alphabetical file listing.)


AI Disclosure
-------------

Much of the code and tests in this repository were written with AI
assistance, under close human supervision.  All checkins that contain AI
generated material explain the division of labor in the git commit
message, including attribution to the particular AI system(s) used.  All
commits are made directly by a human, and that person takes full
responsibility for all committed content, regardless of the level of AI
involvement, to the same degree as if there was no AI involvement.

Exception: Sometimes a git commit message will explicitly say that some
AI-generated material being committed has not yet been reviewed by the
committer.  Such a commit must either be amended, or followed by a
commit (typically with an edit) that indicates approval of the AI
material (as edited), before pushing.  This enables the workflow of
committing a large chunk of AI work first, then reviewing and editing
afterward, both to accurately record the provenance of each code
fragment, and to guard against accidentally breaking working code and
not having an easy way to recover.

Any prose that includes AI-generated text is disclosed as such at the
top of the file (in addition to provenance in git commit messages).

The earliest versions of the structure deduction and minimization
algorithms were informed in part by drafts created by Claude Code.
Claude's original minimization proposal is in doc/claude-min-alg.txt.
Unfortunately, I didn't keep a copy of its proposal for structure
deduction, though my recollection is it focused on delimiter balancing
and indentation (aimed at Python).

During development, I have frequently used Claude Code to get feedback
on design increments.


LICENSE
-------

Copyright 2026 Scott McPeak

https://opensource.org/license/bsd-2-clause


EOF
