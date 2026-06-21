# Training dataset chunker empty-prefix list fast path

This Python performance slice is limited to single-turn long-context chunking in
`worker.model_ops.training_dataset_chunker._chunk_single_turn(...)`.

## Goal

Keep chunking behavior unchanged while avoiding empty-list concatenation when a
single-turn sample has no system prefix. This is the common synthetic/probe path
and many training examples are user/assistant only, so the chunk candidate loop
can build `[user, assistant]` message lists directly instead of evaluating
`system_prefix + [...]` for an empty prefix on every candidate segment.

## Probe coverage

The affected path is covered by the registered PR-scoped performance probe
`training-dataset-chunker-top-level-base-copy` in
`infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`,
`coverage_command`, and `probe_command` entries. This slice extends the focused
test/coverage commands with the no-system-prefix regression case.

## Verification plan

1. Run the focused no-system-prefix regression test.
2. Run the registered focused test command for
   `training-dataset-chunker-top-level-base-copy`.
3. Run changed-scope coverage for the touched Python paths and probe script.
4. Run the registered probe locally on Linux against `origin/main` and this
   branch.
5. Use the PR-scoped performance workflow as the merge gate.

## Linux validation boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
behavior changes are included.
