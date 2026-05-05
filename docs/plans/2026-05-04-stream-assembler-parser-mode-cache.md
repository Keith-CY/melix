# Stream Assembler Parser Mode Cache Plan

## Goal

Reduce repeated parser-mode and structural-prefix derivation in `RequestStreamAssembler` by computing immutable request-mode values once during assembler initialization.

## Linux-only constraint

This slice is Python-only and can be verified locally on Linux with focused pytest, changed-scope coverage, and an explicit synthetic stream assembly probe.

## Touched files

- `services/mlx-worker-python/worker/runtime/stream_assembler.py`
- `services/mlx-worker-python/tests/test_stream_assembler.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Performance probe

Register `stream-assembler-parser-mode-cache` in the PR-scoped performance registry. The probe feeds many cumulative fragments through a tool-enabled assembler, including partial structural tag suffixes and tool-call parsing, and reports elapsed time plus emitted tool-call count.

## Success metrics

- Focused stream assembler tests pass.
- Changed-scope coverage for touched executable Python lines is at least 95%.
- Local synthetic probe shows lower mean elapsed time on head than `origin/main` while preserving the same tool-call count.
- `git diff --check` passes.
