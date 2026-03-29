# M4.9 Vision Integration Evidence

## Goal

Close the vision milestone with live integration evidence for multimodal ingress, OCR defaults, cache-aware vision execution, and tool-calling support.

## Scope

- add end-to-end vision-path integration coverage
- add machine-readable metrics for vision execution and ingress
- keep evidence discoverable from the roadmap and operator docs

## Files

- update `tests/integration/`
- update `services/mlx-worker-python/worker/productization/`
- update `docs/runbooks/`

## Implementation Notes

- evidence should cover local images, remote images, multi-image requests, OCR defaults, and VLM tool calls
- metrics should distinguish preprocess, fetch, prefill, and generation costs
- avoid deterministic-only evidence as the sole proof of completion

## Verification

- `make py-test`
- `make integration-test`
- touched-scope metrics report command for the vision slice

## Acceptance

- the completed vision slice has repository-owned integration evidence and metrics
- operators can inspect the key vision-path measurements without ad hoc scripts
