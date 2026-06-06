# Desktop Polish

## Purpose

Validate the `M15.4` desktop-polish contract for the native Melix operator shell:

- token-stream presentation smoothing remains measurable and intact under bursty delivery
- shared desktop banners keep actionable download-recovery state ahead of dismissible update notices
- download-queue state persists through operator-session restore
- all product-shell surfaces and tool sections remain grounded in real SwiftUI navigation rather than
  inert placeholders

## Smoke Command

Run the repository-owned smoke command:

```bash
python3 scripts/m15_desktop_polish_smoke.py --json
```

The smoke wraps a focused Swift test suite and emits a machine-readable payload with four sections:

- `chat`
  - `presentation_lag_ms`
  - `presentation_flush_count`
  - `render_update_count`
  - `stream_event_count`
  - `token_delta_count`
  - `stream_transcript_bytes`
  - `transcript_parity_mismatch_count`
- `signals`
  - `top_banner_title`
  - `download_recovery_visible`
  - `update_signal_visible`
  - `update_signal_dismissible`
- `persistence`
  - `operator_session_restore_ms`
  - `operator_session_persist_write_ms`
  - `persisted_download_queue_count`
  - `restored_download_queue_count`
  - `restored_selected_tool_section`
- `navigation`
  - `grounded_surface_count`
  - `grounded_tool_section_count`

Expected success values:

- `top_banner_title == "Download Recovery Available"`
- `download_recovery_visible == true`
- `update_signal_visible == true`
- `update_signal_dismissible == true`
- `persisted_download_queue_count == 1`
- `restored_download_queue_count == 1`
- `restored_selected_tool_section == "Downloads"`
- `grounded_surface_count == 5`
- `grounded_tool_section_count == 6`

## Focused Swift Verification

When debugging the smoke directly, run the underlying focused suite:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" \
swift test --package-path apps/macos-menubar --filter DesktopPolishSmokeTests
```

## Integration Verification

The repository integration test executes the same smoke contract:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
uv run --project services/mlx-worker-python pytest tests/integration/test_desktop_polish_smoke.py -q
```

## Troubleshooting

- If `presentation_flush_count <= 1`, inspect the UI-side chat presentation queue in
  `RuntimeViewModel` before assuming worker-side stream chunking regressed.
- If `render_update_count` is close to `token_delta_count` during high-rate local decode,
  inspect the UI cadence gate before changing worker-side stream delivery.
- If `transcript_parity_mismatch_count > 0`, treat the run as a transcript-fidelity regression:
  compare the raw token delta accumulator with the terminal assistant transcript before changing
  markdown rendering.
- If the top banner is not `Download Recovery Available`, inspect the download queue payload from
  `registry_snapshot` and confirm the row still reports `resume_ready=true`.
- If `grounded_surface_count` or `grounded_tool_section_count` drops, inspect the corresponding
  renderable SwiftUI destination view for an accidental placeholder branch or a no-longer-mounted
  public section before changing the smoke expectations.
