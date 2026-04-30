# Issue 71 Owner-Mode Sentinel And PR App Artifact Link Plan

## Goal

Make Python worker stream-ownership observability unambiguous on the Swift side and expose a stable downloadable Melix app artifact link on pull requests.

## Architecture

Keep the existing `python_worker.generation_stream_owner_mode_code` metric but split missing/uninitialized values from future unknown values with distinct sentinel codes. The Swift control plane remains the projection layer from worker runtime stats into numeric observability metrics.

For CI, extend the existing `package-self-contained-app` workflow so PR runs publish a sticky comment containing the uploaded app artifact link from the workflow run.

## Scope

- Add explicit constants or mapping behavior for:
  - missing or empty owner mode values
  - known executor-owned modes
  - unrecognized future owner mode strings
- Update Swift tests that currently collapse empty and unknown values into the same metric code.
- Keep worker protobuf/runtime payloads unchanged; this is a Swift observability contract change only.
- Extend `.github/workflows/package-self-contained-app.yml` so pull requests receive a sticky comment with the packaged app artifact name and download URL.

## Tests

- Request coordinator metric mapping tests prove empty values and unrecognized future values produce different sentinel codes.
- Existing runtime metric propagation tests still pass for known executor-owned modes.
- Workflow YAML parses successfully after the CI change.

## Verification

- `swift test --package-path services/control-plane-swift --filter RequestCoordinatorTests`
- `swift test --package-path services/control-plane-swift --filter OpenAIHandlerTests`
- `python3 - <<'PY'` YAML parse for `.github/workflows/package-self-contained-app.yml`
- `git diff --check`

## Metrics

- Observability correctness metric: empty/missing owner-mode strings and unrecognized future strings are distinguishable in `python_worker.generation_stream_owner_mode_code`.
- PR delivery metric: packaged-app PR runs emit one sticky comment containing a downloadable artifact link.
- Performance metric: N/A for runtime throughput; this slice changes observability mapping and CI artifact discoverability only.
