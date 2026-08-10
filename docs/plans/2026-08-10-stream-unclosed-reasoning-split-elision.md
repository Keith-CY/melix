# Stream assembler unclosed reasoning split elision

## Scope

This slice targets `RequestStreamAssembler._recover_unclosed_reasoning_body` in
`services/mlx-worker-python/worker/runtime/stream_assembler.py`.

Malformed reasoning recovery receives a hidden reasoning body and may split it
from a recovered visible answer at a blank-line marker. The previous path used
`str.split(marker, 1)` after marker detection, which allocated an intermediate
list and two string entries before trimming the returned sides.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`stream-assembler-structural-prefix-cache` in `infra/perf/pr_scoped_probes.json`.
This slice keeps the existing focused `test_command`, `coverage_command`, and
`probe_command` entries, adds this plan to the probe watch globs, and retargets
the structural-prefix probe's `unclosed_reasoning_recovery_elapsed_ms_mean`
scenario to exercise the blank-line recovery path.

## Optimization

Use `str.find(marker)` plus direct slicing to recover the hidden and visible
segments. This preserves the existing marker precedence and trimming semantics
while avoiding the intermediate `split()` allocation.

## Verification

- Focused stream assembler tests must prove the blank-line recovery path returns
  the same trimmed hidden/visible pair without invoking `split()`.
- The registered structural-prefix probe must continue reporting
  `unclosed_reasoning_recovery_elapsed_ms_mean` and the unchanged guard counters.
- Changed-scope coverage must include `stream_assembler.py`, focused tests, the
  PR-scoped performance tests, and the structural-prefix probe script.
