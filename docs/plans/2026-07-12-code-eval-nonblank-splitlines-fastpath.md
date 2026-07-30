# Code Eval Nonblank Test Count Splitlines Fast Path

## Context

The registered PR-scoped probe `code-eval-test-count-nonblank-streaming` covers
`services/mlx-worker-python/worker/engine/code_eval_runner.py` and the fallback
test-counting path used when code-eval test payloads contain no assert statements
or cannot be parsed as Python.

The previous fallback streamed every character to avoid allocating a filtered
line list. That remains the safest path for small inputs and string subclasses
used by regression sentinels, but large exact `str` payloads can use CPython's
C-backed `splitlines()` loop and still avoid materializing a filtered list.

## Scope

- Add a large-payload exact-`str` fast path in `_count_nonblank_test_lines()`.
- Keep the streaming path for short inputs and string subclasses so existing
  guard tests still prove no filtered list is built for sentinel inputs.
- Preserve splitlines/strip semantics for ASCII and Unicode line boundaries.

## Measurement

Registered probe: `code-eval-test-count-nonblank-streaming`

Required commands:

- Focused tests from the registry entry.
- Changed-scope coverage from the registry entry.
- Registered probe command from the registry entry.

Success is accepted only if behavior tests pass, changed-scope coverage remains
above the repository threshold, and the probe reports lower elapsed time for the
60k-line synthetic code-eval fallback workload. The fast path trades a small,
bounded temporary line-split allocation for lower elapsed time on large exact
strings; sentinel subclasses and small inputs keep the zero-split streaming path.

## Linux Boundary

This is a Python worker path and can be validated locally on Linux. GitHub
Actions remains the source of truth for the registered PR-scoped performance
workflow after push.