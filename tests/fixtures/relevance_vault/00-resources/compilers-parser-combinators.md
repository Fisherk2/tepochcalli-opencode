---
title: Parser combinators with backtracking
date: 2026-11-12
tags: [compilers, parsing]
---

# Parser combinators with backtracking

A parser combinator is a function from input to a result plus a remainder, and
composition is ordinary function composition. Alternative is where the cost
appears: without a decision procedure the second branch is tried only after the
first consumes input and fails, and that is backtracking.

## Memoisation and error recovery

Memoisation turns the exponential blowup of nested alternatives into linear work
by caching the result of a parser at an input position — the packrat trick. The
cache is per parse and per position, and it costs memory proportional to input
length times the number of distinct parsers applied there.

Error recovery is the part the papers underplay: a parser that backtracks to the
last committed choice reports the error where the choice was made, not where the
input actually went wrong. Labelling the expectation at each alternative is what
turns the position into a message a user can act on.
