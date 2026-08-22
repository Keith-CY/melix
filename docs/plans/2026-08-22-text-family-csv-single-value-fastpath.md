# Text family CSV single-value fast path

## Slice

This Python-only performance slice is limited to the text-family metadata CSV parser helper in `services/mlx-worker-python/worker/runtime/text_family_adapters.py`.

The common metadata override path often supplies a single parser or namespace value without a comma. Previously `_split_csv(...)` still called `str.split(",")` and then stripped every part. This slice keeps multi-value CSV behavior unchanged while returning the stripped single value directly when the raw value contains no comma.

## Registered performance probe

The affected path is covered by the registered PR-scoped probe `text-family-config-copy-elision` in `infra/perf/pr_scoped_probes.json`. The registry entry has focused `test_command`, `coverage_command`, and `probe_command` entries and watches the text-family adapter, focused tests, and probe script.

The primary metric is `elapsed_ms_mean` from `scripts/text_family_config_probe.py`; `peak_bytes_mean`, `config_copy_calls_mean`, and `config_key_accesses_mean` are regression guards.

## Verification plan

1. Add a focused regression test proving single non-empty CSV values do not call `split(...)` while preserving trimming semantics.
2. Apply the `_split_csv(...)` no-comma fast path only.
3. Run the registered focused pytest command locally on Linux.
4. Run changed-scope coverage for the registered probe locally on Linux.
5. Run the registered `text-family-config-copy-elision` probe locally comparing `origin/main` to this branch.
6. Use GitHub Actions PR-scoped performance as the final registered probe validation and merge gate.
