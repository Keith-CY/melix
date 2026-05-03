# Event Extraction Top20 Built-In Dataset Plan

## Goal

Package the confirmed first 20 `top200_final.jsonl` dialogues as a repository-owned built-in evaluation dataset for the `event_extraction` suite.

## Scope

- Add `services/mlx-worker-python/fixtures/evaluation/top200.event-extraction.top20.v1/`.
- Preserve the existing event extraction JSONL row shape: `dialogue_id`, `dialogue`, and `events`.
- Allow `event_extraction_weighted_f1` runs to use the built-in package when no `--source-jsonl` is provided.
- Keep explicit local JSONL evaluation unchanged for ad hoc full `top200_final.jsonl` runs.
- Make the macOS App Evaluation flow select the top20 dataset and event extraction scorer by default when Event Extraction is the selected suite.
- Keep text-generating multimodal catalog models visible in the Evaluation model picker so downloaded Gemma 4-style VLM entries can be evaluated on text-only event extraction prompts.
- Merge text-generating models from the registry snapshot into App Evaluation catalog selection so already downloaded Gemma 4 cache entries do not require re-entering a Hub repo id.
- Treat indexed Hugging Face cache snapshots as available only when every referenced weight shard exists, so interrupted Gemma 4 downloads are not exposed as runnable Evaluation targets.
- Expose configured remote servers as App Evaluation targets so a Gemma 4 31B remote target can be selected directly instead of being limited to semantic judge configuration.
- Package only the confirmed top20 event extraction fixture into the macOS App bundle; do not bundle the full `top200_final.jsonl` source or remaining 180 dialogues.
- Surface App-launched Evaluation command failures inline in Diagnostics instead of only in the status menu.
- Allow `event_extraction_weighted_f1` to execute against a loaded local model, not only a remote provider target.
- Document the dataset id and usage in the evaluation runbook.

## Dataset Identity

- `dataset_id`: `top200.event-extraction.top20.v1`
- `suite_id`: `event_extraction`
- `sample_count`: `20`
- Source file used for selection: `/Users/ChenYu/Downloads/top200_final.jsonl`
- Source SHA-256: `bbfbdcfbdf23a7443e2523595db4324917c93dc9bf9fd33dce8a5b44f405df5f`
- Dialogue ids, in source order: `1, 2, 3, 4, 6, 8, 9, 10, 12, 15, 17, 18, 19, 20, 21, 22, 23, 25, 27, 29`

## Implementation

1. Add failing worker tests for built-in event extraction dataset resolution and fixture integrity.
2. Add the fixture manifest, README, and `samples.jsonl`.
3. Update `WorkerMaintenanceService.RunEvaluation` so `event_extraction_weighted_f1` accepts a built-in package when the request source is empty.
4. Update CLI/UI defaults so the event extraction suite points at `top200.event-extraction.top20.v1`.
5. Update the App Evaluation model filter so text-capable VLM entries are eligible without admitting audio-only or image-only models.
6. Update the App Evaluation scorer normalization so stale `multiple_choice_accuracy` state becomes `event_extraction_weighted_f1` for the single Event Extraction suite.
7. Merge registry snapshot model entries into App Evaluation catalog selection for downloaded text and text-capable VLM models.
8. Add a Remote Server Evaluation target mode that dispatches `melix eval run --remote-server-id ... --remote-model ...` through the App CLI bridge.
9. Update macOS App bundling to include only `top200.event-extraction.top20.v1` under the bundled repo subset and no full top200 source file.
10. Bundle the `melix` CLI executable into the macOS App resources so App-launched Evaluation does not depend on a missing `.build/.../melix` path inside the packaged repo subset.
11. Resolve built-in dataset paths from `MELIX_REPO_ROOT` so packaged App workers read the bundled top20 fixture instead of depending on process cwd.
12. Render typed CLI workflow failures inside the Evaluation Diagnostics panel with command id, surface, kind, and detail.
13. Require indexed Hugging Face cache snapshots to have all referenced `.safetensors` shards before the registry snapshot advertises them to the App.
14. Update the benchmark/evaluation runbook with a built-in top20 event extraction example.
15. Share event extraction chat-message construction between remote clients and local loaded-model evaluation so the same prompt snapshot is used for both execution paths.

## Verification

- Focused Python tests for `test_evaluation_core.py`.
- Focused Swift CLI parser/runner tests for event extraction defaults.
- Focused macOS menu bar view-model tests for Evaluation model eligibility and event extraction scorer defaults.
- Focused macOS menu bar view-model tests for downloaded registry Gemma 4 Evaluation selection and remote-server Evaluation target dispatch.
- Focused macOS Diagnostics rendering test for inline Evaluation CLI failure details.
- Focused macOS App bundle test proving only the top20 fixture is copied and the full top200 source is excluded.
- Focused model registry tests proving interrupted indexed Hugging Face cache snapshots are skipped until all weight shards exist.
- Focused worker test proving `event_extraction_weighted_f1` can use a loaded local VLM model and records live runtime evidence.
- JSONL integrity check confirming 20 rows and the confirmed dialogue id sequence.

## App Smoke Findings

- PR #146 used `mlx-community/gemma-4-26b-a4b-it-4bit` for the local chat smoke; that cache entry is not present in the current machine state.
- The current local Hugging Face cache contains an interrupted `unsloth/gemma-4-E4B-it-MLX-8bit` snapshot: config and index files exist, but referenced weight shards are still `.incomplete`.
- The configured Gemma 4 31B target is a remote server target, not a local cache snapshot, so running the top20 event extraction Evaluation through it sends the 20 prompts to that configured provider.
- Computer Use can list the unsigned temporary App bundle but cannot attach to its window state, so the smoke used the same App window through macOS Accessibility. The App itself should remain testable through normal signed/local builds.
- `unsloth/gemma-4-E4B-it-MLX-8bit` was downloaded to a complete Hugging Face cache snapshot and verified with `hf cache verify`.
- App worker smoke with `/private/tmp/MelixGemma4Eval.app` loaded `unsloth/gemma-4-E4B-it-MLX-8bit` as `mlx_vlm` from the local cache and returned `ok` for a chat smoke.
- The first App top20 run failed because `event_extraction_weighted_f1` required a remote provider target. After adding local loaded-model support, the App completed `eval-0002` for all 20 built-in dialogues.
- `eval-0002` produced `overall_weighted_f1=0.288104`, `events_evaluated=92`, `events_matched=40`, `events_unmatched_gold=18`, `events_unmatched_pred=34`, `events_written=74`, and `events_failed=2`.
- The two normalization failures were both from dialogue `20`, where the model emitted `location` as a scalar string instead of the required string array. This did not abort the run, but it indicates the UI/report should make schema normalization failures more visible.
- The full App run took `234.010718s`; trace diagnostics reported mean request duration `11698.0916ms`, p95 `16593.6317ms`, and max `18369.529ms`. The CLI did not show per-dialogue progress while the run was active.

## Metrics

- Dataset packaging metrics: `sample_count=20`; event count distribution will be checked from the packaged JSONL.
- Gemma 4 E4B App local evaluation metrics: `sample_count=20`; `duration_seconds=234.010718`; `overall_weighted_f1=0.288104`; `failure_count=2`.
