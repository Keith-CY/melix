# Melix Task 6 Execution Plan: Integration and Developer Workflow Completion

## Scope

This plan completes the phase-0 workflow around the already functional thin path.

The slice remains narrow:

- keep deterministic mode as the default integration path
- expand integration coverage into explicit streaming, abort, and models scenarios
- add reproducible local bring-up and cleanup scripts for the worker and control plane
- keep MLX smoke verification optional and explicitly configured

This slice does not add:

- CI matrix expansion
- production benchmarking harnesses
- cache or scheduler stress testing
- new public HTTP endpoints

## Architecture Boundaries

- Integration tests continue to exercise the real local HTTP listener and the real worker bridge.
- Deterministic backend remains the stable test backend.
- MLX verification stays outside the default integration run and is only documented as an optional operator path.
- Local scripts must start only the control plane and one worker process for the thin path.

## Planned Changes

### Integration test structure

- Extract reusable subprocess/bootstrap helpers from the current live-path test into a shared helper module.
- Split the current coverage into three explicit tests:
  - streamed chat completions
  - abort of an in-flight streamed request
  - `/v1/models` visibility and warm-state reflection
- Keep integration tests self-cleaning and resilient to early child-process exits.

### Developer scripts

- Add `scripts/dev_up.sh` to:
  - choose a socket path and HTTP port
  - start the deterministic worker
  - start the control plane
  - write PID and environment metadata into a temporary runtime directory
- Add `scripts/dev_down.sh` to:
  - stop any running phase-0 worker/control-plane processes started by `dev_up.sh`
  - remove the runtime directory and socket

### Performance probes and metrics

Required probes for this slice:

- control-plane startup to HTTP readiness
- worker startup to warm-model visibility
- end-to-end abort latency in integration

Initial success targets:

- deterministic integration suite completes without flaky retries
- abort integration completes within 1 second after the cancel request is issued
- touched integration/workflow scope remains at or above 95 percent automated coverage where measurable

If the startup and abort timings are only measured in integration assertions rather than exported metrics, the metrics report may use those observed timings directly.

## Verification Plan

Targeted verification:

```bash
make integration-test
```

Broader regression checks:

```bash
make py-test
make swift-test
make coverage
```

Optional local workflow verification:

```bash
bash scripts/dev_up.sh
curl -sS http://127.0.0.1:$MELIX_HTTP_PORT/v1/models
bash scripts/dev_down.sh
```

## Exit Conditions

Task 6 is complete when:

- integration coverage includes streaming, abort, and models-state scenarios as separate tests
- the local bring-up and cleanup scripts work for the deterministic thin path
- the default integration path remains deterministic and green
- the optional MLX smoke path is documented without becoming a required default dependency
