# Metrics Artifact Archive

Generated metrics JSON artifacts are benchmark evidence, not runtime inputs.
Do not keep large generated JSON files in this directory unless a release
process explicitly requires a checked-in snapshot.

TurboQuant Phase 2 raw metrics evidence that previously lived under this
directory is archived in GitHub issue
[#46](https://github.com/Keith-CY/melix/issues/46). Each issue comment contains
one original JSON artifact and preserves its former repository path.

When producing new benchmark evidence:

1. Write generated JSON to a temporary or local output path.
2. Summarize the result in the relevant plan, architecture note, or runbook.
3. Archive raw JSON evidence in a GitHub issue when it needs to remain
   reviewable after the local run.

The archived TurboQuant Phase 2 artifacts are:

- `docs/metrics/phase2-active-kv-blocked-fallback-speedup-postopt.json`
- `docs/metrics/phase2-active-kv-candidate-check-postopt.json`
- `docs/metrics/phase2-active-kv-candidate-check-probe-preopt.json`
- `docs/metrics/phase2-active-kv-decode-guard-postopt.json`
- `docs/metrics/phase2-active-kv-fused-turboquant-candidate.json`
- `docs/metrics/phase2-active-kv-lazy-eval-probe.json`
- `docs/metrics/phase2-active-kv-qwen35-hybrid-stability-summary.json`
- `docs/metrics/phase2-active-kv-qwen35-hybrid-turboquant-routing.json`
- `docs/metrics/phase2-active-kv-qwen35-support-smoke.json`
- `docs/metrics/phase2-active-kv-qwen35-turboquant-speedup-postopt.json`
- `docs/metrics/phase2-active-kv-qwen35-turboquant-speedup-preopt.json`
- `docs/metrics/phase2-active-kv-qwen35-turboquant-speedup-stability-summary.json`
- `docs/metrics/phase2-active-kv-runtime-speedup-postopt.json`
- `docs/metrics/phase2-active-kv-terminal-model-call-postopt.json`
- `docs/metrics/phase2-active-kv-terminal-model-call-preopt.json`
- `docs/metrics/phase2-active-kv-vendored-turboquant-append-slice.json`
- `docs/metrics/phase2-active-kv-vendored-turboquant-cache-probe.json`
- `docs/metrics/phase2-active-kv-vendored-turboquant-eval-probe.json`
- `docs/metrics/phase2-active-kv-vendored-turboquant-fused-quantize-experiment.json`
- `docs/metrics/phase2-active-kv-vendored-turboquant-online-softmax.json`
- `docs/metrics/phase2-active-kv-vendored-turboquant-packed-word-lanes.json`
- `docs/metrics/phase2-active-kv-vendored-turboquant-runtime.json`
- `docs/metrics/phase2-active-kv-vendored-turboquant-shared-scores.json`
- `docs/metrics/phase2-active-kv-vendored-turboquant-storage-fastpath.json`
- `docs/metrics/phase2-affine-q4-preopt.json`
