# Phase 7 Image Operator Workflow

## Trigger

Use this runbook when you need to:

- boot the Phase 7 stack and exercise image generation plus image editing end to end
- reproduce variation, iterate, redo, timeout, queueing, and cancellation evidence for iterative
  image workflows
- capture the reproducible Phase 7 latency, artifact-publish, and peak-memory report
- inspect artifact lineage and timeout policy from the shipped HTTP image payloads

## Preconditions

- macOS on Apple Silicon
- `make bootstrap` has completed successfully
- `make proto` has completed successfully
- `make swift-test` and `make py-test` are green

## Diagnosis

1. Refresh the local build and generated protocol artifacts.

```bash
make bootstrap
make proto
make swift-test
make py-test
```

2. Start a fresh local stack under a dedicated Phase 7 runtime directory.

```bash
MELIX_RUNTIME_DIR=.runtime/phase7-ops bash scripts/dev_up.sh
```

3. Confirm that the control plane exposes the expected local image model.

```bash
curl -sS http://127.0.0.1:12436/v1/models
```

4. Run the reproducible Phase 7 metrics command.

```bash
make phase7-metrics
```

5. Run the focused image-iteration smoke if you need repository-owned HTTP evidence for variation,
   iterate, redo, or timeout behavior.

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
uv run --project services/mlx-worker-python --extra mlx \
pytest tests/integration/test_phase7_operator_workflows.py -k 'iteration or timeout' -q
```

6. Inspect the runtime directory and logs if any image path fails.

```bash
ls -la .runtime/phase7-ops
tail -n 50 .runtime/phase7-ops/control-plane.log
tail -n 50 .runtime/phase7-ops/python-worker.log
tail -n 50 .runtime/phase7-ops/swift-text-worker.log
```

## Expected Evidence

- `image_generate` reports request latency, job latency, artifact publish latency, peak memory,
  output bytes, the generated `artifact_id`, and the effective creative timeout policy
- `image_variation` reports request latency, job latency, artifact publish latency,
  `source_artifact_id`, and the generated artifact `parent_artifact_id`
- `image_iterate` reports request latency, job latency, artifact publish latency,
  `source_artifact_id`, `source_job_id`, generated `parent_artifact_id`, and `prompt_delta`
- `image_redo` proves a follow-up iterate request can be reconstructed from persisted job metadata
  rather than desktop-local draft state
- `image_queue` reports a non-zero queue wait after a follower request waits behind a slower image job
- `text_under_image` reports a non-`N/A` TTFT measurement while image work is active
- `image_cancel` reports a successful cancel attempt and a `409` cancelled terminal response
- `image_timeout` reports a `504` response with `deadline_exceeded` under the short timeout override

The focused image-iteration smoke should surface these HTTP payload fields directly:

- `job.request_timeout_seconds`
- `job.source_artifact_id`
- `job.source_job_id`
- `job.prompt_delta`
- `job.edit_mode`
- `job.recipe`
- `data[*].artifact.parent_artifact_id`

## Recovery

1. Stop the stack and clear stale runtime metadata.

```bash
MELIX_RUNTIME_DIR=.runtime/phase7-ops bash scripts/dev_down.sh
```

2. Reboot the reproducible image fixture path and rerun the metrics command when you need a bounded debugging baseline.

```bash
MELIX_RUNTIME_DIR=.runtime/phase7-ops \
MELIX_DETERMINISTIC_IMAGE_DELAY_MS=120 \
bash scripts/dev_up.sh
make phase7-metrics
```

3. If variation, iterate, or redo evidence is missing, rerun the focused integration smoke and
   inspect the returned lineage or timeout fields before assuming the desktop surface is at fault.

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
uv run --project services/mlx-worker-python --extra mlx \
pytest tests/integration/test_phase7_operator_workflows.py -k 'iteration or timeout' -q
```

4. Use the native Image panel only after the control plane reports warm models.

```bash
swift run --package-path apps/macos-menubar melix-menubar
```

## Verification

```bash
make swift-test
make py-test
make integration-test
make coverage
make phase7-metrics
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
uv run --project services/mlx-worker-python --extra mlx \
pytest tests/integration/test_phase7_operator_workflows.py -k 'iteration or timeout' -q
MELIX_RUNTIME_DIR=.runtime/phase7-ops bash scripts/dev_down.sh
```
