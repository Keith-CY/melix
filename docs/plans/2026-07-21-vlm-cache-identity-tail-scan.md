# Deterministic VLM Cache Identity Tail Scan

## Scope

This Python-only performance slice is limited to `services/mlx-worker-python/worker/runtime/deterministic_vlm_runtime.py` and the direct focused test coverage in `services/mlx-worker-python/tests/test_vision_runtime.py`.

## Registered Probe

The affected path is already covered by the registered PR-scoped performance probe `deterministic-vlm-completion-token-scan` in `infra/perf/pr_scoped_probes.json`. The probe watches the deterministic VLM runtime and has focused `test_command`, `coverage_command`, and `probe_command` entries. Local Linux can run the focused tests, changed-scope coverage, and registered probe; GitHub Actions PR-scoped performance remains the merge gate.

## Optimization

`_cache_identity_fingerprint_hash_hex(...)` only needs the final colon-delimited field from a VLM cache identity when media inputs are present. The previous implementation used `cache_identity.split(":")[-1]`, materializing all identity segments. This slice changes the extraction to `cache_identity.rsplit(":", 1)[1]`, preserving the returned fingerprint while scanning only from the tail and avoiding full split-list materialization.

## Verification Plan

1. Run the registered focused test command, including a direct regression test that confirms the helper uses a single tail split and preserves fingerprint extraction.
2. Run the registered changed-scope coverage command.
3. Run the registered `deterministic-vlm-completion-token-scan` probe locally on Linux and compare against the baseline probe from `origin/main`.
4. Use PR-scoped performance CI as the final registered probe validation before merge.
