# Event extraction matching edge-state precompute

## Scope

This slice keeps event-extraction matching semantics unchanged while reducing repeated work in `_maximum_weight_event_matching()`.

The affected code path is covered by the registered PR-scoped probe `event-extraction-alignment-accepted-edge-cache` in `infra/perf/pr_scoped_probes.json`. The probe includes focused test, coverage, and JSON metric commands for `services/mlx-worker-python/worker/productization/event_extraction.py`.

## Change

Precompute the accepted edge state once per matching call:

- prediction index
- prediction bit mask
- floating score
- rounded score used in returned match tuples

The recursive solver then reuses the precomputed mask and rounded score instead of rebuilding them for every explored DP branch.

## Behavior

No scoring or tie-breaking behavior is intended to change. `_accepted_event_matching_edges()` retains its public test-facing shape of `(pred_index, score)` rows.

## Verification

Run the registered probe's focused tests, changed-scope coverage, and probe command locally on Linux before opening the PR. GitHub Actions' PR-scoped performance workflow remains the merge gate.
