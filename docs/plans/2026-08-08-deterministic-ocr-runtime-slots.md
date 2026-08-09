# Deterministic OCR Runtime Slots

## Scope

This Python-only performance slice targets the deterministic OCR runtime hot path
in `services/mlx-worker-python/worker/runtime/deterministic_ocr_runtime.py`. The
affected path is covered by the registered PR-scoped probe
`deterministic-ocr-token-count-scan` in `infra/perf/pr_scoped_probes.json`,
including focused `test_command`, `coverage_command`, and `probe_command`
entries.

## Change

`DeterministicOCRRuntime` now declares explicit slots for its cached prompt-token
state and last probe snapshot. This preserves runtime behavior while publishing
the hot-path state layout explicitly and keeping repeated prompt-token cache
reads on fixed subclass slot descriptors.

## Verification

The slot-layout assertion lives in
`services/mlx-worker-python/tests/test_deterministic_ocr_runtime.py` so the
shared vision-runtime test module does not force unrelated VLM/vision-family
registered probes to cover deterministic OCR-only assertions.

- Run the registered focused deterministic OCR test command.
- Run the registered changed-scope coverage command for the deterministic OCR
  token-count scope.
- Run `scripts/deterministic_ocr_token_count_probe.py` on Linux before and after
  the change and compare `elapsed_ms_mean` and `peak_bytes_mean`.
- Rely on the registered PR-scoped performance workflow in CI for PR validation.
