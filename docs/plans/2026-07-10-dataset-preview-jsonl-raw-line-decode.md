# Dataset preview JSONL raw-line decode

## Scope

This Python-only performance slice is limited to the JSONL row reader used by
`services/mlx-worker-python/worker/dataset_registry/catalog.py` during dataset
preview reads.

Registered PR-scoped probe: `dataset-registry-preview-limit-short-circuit` in
`infra/perf/pr_scoped_probes.json`. The registry entry already includes focused
`test_command`, `coverage_command`, and `probe_command` entries for this path.

## Root cause

The JSONL preview path already receives newline-delimited JSON records, but it
called `raw_line.strip()` for every non-empty candidate before decoding. That
allocates a second string on the hot path even though `json.loads()` accepts
leading and trailing whitespace, including the line terminator. Blank or
whitespace-only records still need to be skipped before decoding.

## Slice

Replace the per-row strip/empty check with `raw_line.isspace()` for blank-line
skipping and pass the original line directly to `json.loads()`. This preserves
behavior for blank lines, whitespace-padded JSON objects, non-dict entries, and
multi-row limits while avoiding a redundant string allocation for each decoded
JSONL row.

## Verification plan

- Run the focused dataset-registry JSONL regression test and the registered
  dataset preview test command locally on Linux.
- Run the registered changed-scope coverage command locally on Linux.
- Run the registered `dataset-registry-preview-limit-short-circuit` probe locally
  on Linux against `origin/main` and this branch, then use the GitHub PR-scoped
  performance workflow as the merge gate.
