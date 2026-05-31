# Dataset split alias lowercase fast path

## Scope

This Python-only performance slice is limited to `worker.dataset_registry.catalog._split_alias_from_candidate(...)`, the hot helper used while inferring dataset split/config metadata for Hugging Face snapshot files.

## Registered probe

The affected path is covered by the registered PR-scoped performance probes `dataset-registry-snapshot-inference-single-pass` and `dataset-registry-limited-read-streaming` in `infra/perf/pr_scoped_probes.json`. Both probes watch `services/mlx-worker-python/worker/dataset_registry/catalog.py` and include focused `test_command`, `coverage_command`, and `probe_command` entries. The snapshot inference probe is the primary validation source for this slice because it repeatedly infers split/config metadata across synthetic snapshot files.

## Plan

Dataset snapshot paths normally use lowercase split prefixes such as `train`, `validation`, and `test`. The current alias helper lowercases every candidate prefix before looking it up, even when the prefix is already in canonical lowercase form. Add a direct alias lookup first and only allocate a lowercase fallback for uncommon mixed-case inputs.

Behavior stays equivalent because the fallback keeps the existing case-insensitive matching semantics for mixed-case dataset paths and unknown lowercase prefixes still return no alias.

## Verification

Run the registered focused dataset-registry tests, changed-scope coverage, and the registered snapshot-inference probe locally on Linux before pushing. GitHub Actions PR-scoped performance remains the merge gate.
