# P7-M7 Integration and Operator Evidence Implementation Plan

**Goal:** Close Phase 7 with a reproducible operator workflow that exercises image generation, image editing, queueing, cancellation, and text responsiveness under image load while exporting non-`N/A` image latency and resource evidence.

**Scope:** This milestone covers the final Phase 7 metrics surfaces, a `make phase7-metrics` command, live integration smoke tied to the metrics export, and an operator runbook for stack boot, image-job reproduction, metrics capture, and recovery. It does not add new public endpoints or new desktop panels.

## Context

- Phase plan: `docs/plans/2026-03-27-phase-7-image-generation-editing.md`
- Milestone ladder: `docs/plans/2026-03-28-post-phase-0-coding-milestones.md`
- Relevant code:
  - `tests/integration/*`
  - `tests/integration/helpers.py`
  - `scripts/dev_up.sh`
  - `scripts/dev_down.sh`
  - `services/control-plane-swift/Sources/HTTPGateway/*`
  - `services/control-plane-swift/Sources/ImageJobs/*`
  - `services/control-plane-swift/Sources/Requests/*`
  - `services/mlx-worker-python/worker/runtime/*`

## Non-Goals

- Add a new image-job control-plane HTTP family beyond the existing image endpoints.
- Build the Phase 8 model-ops, training, or HuggingFace workflows.
- Replace the existing native Image panel with new UI surfaces.
- Add cloud telemetry export or external dashboards.

## Performance Probes

- `images.request_latency_ms`
- `images.job_latency_ms`
- `images.queue_wait_ms`
- `images.artifact_publish_ms`
- `images.peak_memory_bytes`
- `images.output_bytes`
- `scheduler.text_ttft_under_image_load_ms`

## Work Plan

### Task 1: Surface worker-side image job probes through the runtime stats path

- Extend the shared worker runtime stats schema with image-job latency, artifact publish latency, output bytes, and peak memory fields.
- Record deterministic image-runtime probes in the Python worker registry after generation and edit requests complete.
- Map the image runtime stats into control-plane metrics without changing the public image endpoint payloads.

### Task 2: Add live integration smoke for image workflows and interference

- Add live image smoke that covers generation plus editing through the control plane.
- Add a live queueing case where one delayed image job forces a follower request to wait and assert that queue wait is recorded.
- Add a live text-under-image-load case and assert that `scheduler.text_ttft_under_image_load_ms` is recorded.
- Add a live cancel case that forces an image request to terminate with a cancelled response.

### Task 3: Add the Phase 7 metrics report command

- Add `make phase7-metrics`.
- Implement `scripts/phase7_metrics_report.py` to:
  - boot the live stack
  - run generation, editing, queueing, text-under-image-load, and cancellation probes
  - print a compact report with latency, artifact publish, queue wait, cancel success, and peak memory values
- Keep the deterministic image runtime as the default reproducible operator mode.

### Task 4: Add the operator runbook and docs wiring

- Add a dedicated Phase 7 runbook for image stack boot, smoke reproduction, metrics capture, and shutdown.
- Update docs indexes so the milestone plan, runbook, and metrics command are discoverable.
- Keep the runbook aligned with `scripts/dev_up.sh`, `scripts/dev_down.sh`, and `make phase7-metrics`.

## Verification

```bash
make proto
make swift-test
make py-test
make integration-test
make coverage
make phase7-metrics
git diff --check
```

## Acceptance

- The live stack can reproduce image generation, image editing, queueing, cancellation, and text-under-image-load evidence without manual patching.
- The Phase 7 metrics report contains non-`N/A` image-job latency, queue wait, artifact publish, peak-memory, and cancel-success values.
- The touched scope remains at or above `95%` measured coverage where coverage is currently measurable.
