# Video Understanding Evidence

Run the repository-owned `M16.4` smoke workflow when you need reproducible operator evidence for
the current video-understanding surface without reading runtime code or reconstructing the control
plane metrics by hand.

## Scope

The smoke covers four evidence paths:

- one short local video path request
- one remote video URL request served by a repository-owned local fixture server
- one bounded multi-frame inline workload with explicit `frame_budget`, `start_ms`, and `end_ms`
- one concurrent video-plus-text routing probe that records scheduler protection metrics

The smoke does not claim real frame decoding or media-content understanding. It records the current
bounded request semantics, preprocessing counters, routing protection, and cleanup visibility that
Melix actually exposes today.

## Command

Run the canonical smoke command from the repository root:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
uv run --project services/mlx-worker-python python scripts/m16_video_runtime_smoke.py --json
```

The smoke starts a local Melix stack, provisions fixture video references, and emits one
machine-readable JSON payload to stdout.

## Output

The payload includes:

- `checks`
  - `video.local_path_success`
  - `video.remote_url_success`
  - `video.bounded_window_success`
  - `video.routing.text_protection_success`
- `metrics`
  - per-scenario request latency for local-path, remote-URL, bounded-window, and routing probes
  - `vision.video_first_token_ms`
  - `vision.preprocess_latency_ms`
  - `vision.video_frame_count`
  - `vision.video_frame_budget`
  - `vision.video_window_ms`
  - `vision.temp_media_artifact_count`
  - `vision.temp_media_artifact_bytes`
  - `vision.temp_media_cleanup_latency_ms`
  - `vision.temp_media_cleanup_failure_count`
  - `scheduler.text_ttft_under_multimodal_ms`
  - `scheduler.multimodal_queue_delay_ms`
- `scenarios`
  - raw scenario evidence, source references, and response excerpts for each probe

## Interpretation

Use the smoke output to answer these operator questions:

- Does Melix still accept local-path video references through the live HTTP path?
- Does remote-URL video ingress still work without depending on an external network resource?
- Are bounded multi-frame requests preserving the requested frame budget and clip window?
- Are temporary-media cleanup counters visible for inline video workloads?
- Does text traffic still surface measurable protection metrics while video work is active?

The bounded-window scenario is the canonical source for:

- `vision.video_frame_count`
- `vision.video_frame_budget`
- `vision.video_window_ms`
- `vision.temp_media_*`

The routing scenario is the canonical source for:

- `scheduler.text_ttft_under_multimodal_ms`
- `scheduler.multimodal_queue_delay_ms`

## Diagnosis

If the local-path scenario fails:

- verify the path exists on disk and ends with a supported container suffix such as `.mp4`
- inspect the response excerpt for normalization failures around `input_video.url`

If the remote-URL scenario fails:

- confirm the smoke still points at the local fixture server `http://127.0.0.1:*`
- do not replace the fixture with an internet-hosted URL; repository-owned evidence must stay
  offline and deterministic

If the bounded-window scenario fails:

- compare `vision.video_frame_count`, `vision.video_frame_budget`, and `vision.video_window_ms`
  against the expected `6`, `6`, and `4000`
- inspect the response excerpt for the rendered `Frame policy: uniform_sample ...` line

If cleanup evidence regresses:

- inspect `vision.temp_media_artifact_count`
- inspect `vision.temp_media_artifact_bytes`
- inspect `vision.temp_media_cleanup_latency_ms`
- inspect `vision.temp_media_cleanup_failure_count`

If routing evidence regresses:

- inspect `scheduler.text_ttft_under_multimodal_ms`
- inspect `scheduler.multimodal_queue_delay_ms`
- inspect the routing scenario text excerpt to confirm the text request still reached the live path

## Verification

The repository-owned verification entry points for this surface are:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
uv run --project services/mlx-worker-python pytest \
  services/mlx-worker-python/tests/test_acceptance_metrics.py \
  tests/integration/test_video_runtime_smoke.py -q
```

These checks prove both the machine-readable report contract and the live smoke workflow.
