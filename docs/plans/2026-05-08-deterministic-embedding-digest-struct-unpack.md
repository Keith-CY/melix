# Deterministic Embedding Digest Struct Unpack

## Goal

Reduce per-vector integer decoding overhead in deterministic embedding digest projection while preserving exact deterministic vector values.

## Linux-only constraint

This is a Python worker-runtime slice. It can be validated on Linux with focused pytest, changed-scope coverage, and a local registered PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/runtime/embedding_backends.py`
- `docs/plans/2026-05-08-deterministic-embedding-digest-struct-unpack.md`

## Optimization hypothesis

`DeterministicEmbeddingBackend._project_digest(...)` derives eight little-endian `uint32` values from a SHA-256 digest. The previous loop sliced four bytes at a time and called `int.from_bytes(...)` for each chunk. Because SHA-256 always returns exactly 32 bytes, a single `struct.unpack("<8I", digest)` can decode the eight integers without per-chunk slice allocations and repeated conversion dispatch.

The rest of the projection remains unchanged: base values, squared-sum normalization, rounding, repeat expansion, and zero-norm fallback all preserve the existing deterministic embedding contract.

## Performance probe

Use the existing registered PR-scoped probe `deterministic-embedding-project-digest-allocation` in `infra/perf/pr_scoped_probes.json`. It already has focused `test_command`, `coverage_command`, and `probe_command` entries for `embedding_backends.py`.

The probe reports:

- `elapsed_ms_mean` — lower is better
- `peak_bytes_mean` — lower is better
- `vector_count` / `dimensions` — workload context

Success means exact projection parity tests remain green, changed-scope coverage stays at or above 95%, and the registered probe shows a lower elapsed mean without checksum drift.

## Verification commands

- Focused pytest from the registered probe command.
- Changed-scope coverage from the registered probe command.
- Local registered probe via `scripts/pr_scoped_performance_run.py --probe-id deterministic-embedding-project-digest-allocation`.
- `git diff --check`.
