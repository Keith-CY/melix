# Embedding Project Digest Default-Dimension Fast Path

This Python-only performance slice is limited to `worker.runtime.embedding_backends.DeterministicEmbeddingBackend._project_digest()`.

## Registered probe

The affected path is covered by the registered PR-scoped probe `deterministic-embedding-project-digest-allocation` in `infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`, `coverage_command`, and `probe_command` entries.

This slice extends the checked-in probe script so the registered probe reports both:

- the existing large 4097-dimension projection workload; and
- a default 8-dimension projection workload matching the common deterministic embedding family default.

## Slice

The projection helper already builds one normalized 8-value digest block before repeating it across requested dimensions. When the requested dimension is exactly one digest block, returning that freshly built normalized block avoids the extra `normalized_base * 1` list copy while preserving the legacy projection values and list return type.

For other exact multiples of 8, the helper returns `normalized_base * full_repeats` directly. Remainder-bearing dimensions keep the existing append behavior.

## Verification plan

1. Run focused embedding runtime and PR-scoped probe tests on Linux.
2. Run changed-scope coverage for the changed source, tests, probe, and plan.
3. Run the registered probe locally on Linux against `origin/main` and this branch.
4. Use GitHub Actions PR-scoped performance as the final merge gate.

## Success criteria

- Legacy projection parity remains unchanged for dimensions `0, 1, 8, 9, 17, 384, 1536, 4096, 4097`.
- Local registered probe reports lower default-dimension elapsed time without increasing large-dimension behavior materially.
- PR-scoped performance CI completes successfully before merge.
