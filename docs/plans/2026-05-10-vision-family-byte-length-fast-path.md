# Vision Family Byte-Length Fast Path

## Scope

This Python-only slice narrows `ResolvedVisionFamilyConfig.prompt_token_count(...)` in
`services/mlx-worker-python/worker/runtime/vision_family_adapters.py`.

The function already avoids `prompt_text.split()` list materialization for prompt
tokens. This follow-up keeps the same semantics and removes the per-image
`PreparedImageInput.byte_length` property call while summing image token costs by
reading `len(image.bytes_data)` directly in the hot loop.

## Registered probe

The affected path is covered by PR-scoped probe
`vision-family-prompt-token-count-scan` in `infra/perf/pr_scoped_probes.json`.
The probe has focused `test_command`, `coverage_command`, and `probe_command`
entries, and this slice pins the probe runner to `ubuntu-latest` so the
registered CI report can validate the Python path.

## Verification plan

- Run the registered focused pytest command locally on Linux.
- Run the registered changed-scope coverage command locally on Linux and require
  at least 95% for the touched executable scope.
- Run `scripts/vision_family_prompt_token_count_probe.py` before and after the
  change and compare `elapsed_ms_mean`, `peak_bytes_mean`, `split_calls_mean`,
  and `token_count`.
- Use the PR-scoped performance workflow as the merge gate after push.

## Success criteria

- Focused tests pass.
- Changed-scope coverage remains at or above 95%.
- The local registered probe preserves `split_calls_mean == 0.0` and
  `token_count == 1309.0`.
- `elapsed_ms_mean` improves or remains within noise while preserving semantics.
