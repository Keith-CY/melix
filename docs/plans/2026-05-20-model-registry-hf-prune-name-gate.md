# Model registry HF prune name gate performance slice

## Scope

This Python-only slice keeps model registry discovery semantics unchanged while
reducing per-directory overhead in
`worker.model_registry.catalog.WorkerModelCatalog._scan_registry_root_tree_with_hf_repos`.
Plain local registry scans no longer run the Hugging Face cache subtree relative
path check for every visited directory; the check is now gated to directory names
that can actually represent pruned HF cache subtrees (`snapshots` or `refs`).

## Registered probe

Affected path coverage is provided by the existing registered PR-scoped probe
`model-registry-plain-local-manifest-stat-elision` in
`infra/perf/pr_scoped_probes.json`. The entry includes focused `test_command`,
`coverage_command`, and `probe_command` commands covering
`services/mlx-worker-python/worker/model_registry/catalog.py` and its focused
model registry tests.

## Verification plan

- Add a regression test proving plain local scans do not invoke the HF prune
  relative-path helper for ordinary directories.
- Run the registered probe's focused pytest command locally on Linux.
- Run the registered probe's changed-scope coverage command locally on Linux.
- Compare the registered probe command on `origin/main` and this branch before
  opening the PR.

## Validation boundary

This slice is Python-only and locally verifiable on Linux. No Swift runtime
performance effect is claimed.
