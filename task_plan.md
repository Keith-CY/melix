# Task Plan

## Goal

Close `docs/plans/2026-04-04-live-benchmark-repair.md` so direct Hugging Face benchmark targets execute end to end through the public `melix` CLI and save operator-readable reports into `/tmp`.

## Scope

- restore any missing Python maintenance bridge commands required by the current control-plane worker client
- repair the direct Hugging Face benchmark path for imported text-backed `gemma4` VLM repos
- verify the public `melix bench run --repo-id ...` flow for both target repositories
- capture focused changed-line coverage and repository progress evidence before commit

## Phases

1. Slice 1: restore Python maintenance bridge command coverage
   - status: completed
   - evidence:
     - `services/mlx-worker-python/worker/control_plane_bridge.py` now forwards `export-results` and `submit-results`
     - `services/mlx-worker-python/tests/test_control_plane_bridge_phase5.py` covers both unary bridge commands
     - `services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift` decodes the corresponding bridge responses
2. Slice 2: repair the direct Hugging Face benchmark execution path
   - status: completed
   - evidence:
     - `services/mlx-worker-python/worker/engine/maintenance_core.py` preserves `PreparedVisionRequest` values when annotating text benchmark prompts
     - `services/mlx-worker-python/tests/test_maintenance_service.py` covers imported text-backed `gemma4` benchmark execution
3. Slice 3: verification, live proofs, and operator evidence
   - status: completed
   - evidence:
     - focused Swift and Python verification passed
     - changed-line coverage for the touched executable scope is `100.00%`
     - fresh reports exist at `/tmp/melix-gemma4-bench-report.md` and `/tmp/melix-qwen35-9b-bench-report.md`

## Acceptance

- `melix bench run --repo-id unsloth/gemma-4-E4B-it-MLX-8bit ...` succeeds
- `melix bench run --repo-id Brooooooklyn/Qwen3.5-9B-unsloth-mlx ...` succeeds
- both final report files are copied into `/tmp`
- changed-line coverage for the touched executable scope remains at or above `95%` before commit

## Risks

- direct Hugging Face benchmark imports can fail at the bridge layer even when the worker runtime succeeds, so the public CLI path must be verified explicitly
- text-backed multimodal repos can regress if benchmark prompt shaping strips image-aware request metadata

## Outcome

- all slices are complete
- the live benchmark repair transaction is ready to commit
