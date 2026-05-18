# Multi-Model Server Router

## Goal

Upgrade a Melix server session from a single served-model binding into a
multi-model OpenAI-compatible serving router. A server owns one listener and a
model roster. Requests select the inference model through the payload `model`
field, while the server manages allowed models, defaults, residency, and idle
unload policy.

## Architecture

- Replace the primary server-session contract with `default_model_id`,
  `served_model_ids`, and `model_idle_timeout_seconds`.
- Keep model discovery global in `ModelCatalog`, but make request admission
  server-scoped: a request model must be present in the active server roster.
- Route every OpenAI-compatible endpoint through the same server model resolver
  before worker selection or on-demand loading.
- Treat server sleep and model idle as separate states. A server can remain
  running while one or more models unload after idle timeout.
- Preserve pinned and active-request models. Idle unload only applies to resident
  non-pinned models with no active requests.

## Implementation Notes

- `GatewayConfigStore` is the control-plane persistence owner for listener and
  roster state.
- `OnDemandModelLoader` remains the load path; it is extended with an idle sweep
  helper that reuses the existing worker unload path.
- `OpenAIHandler` resolves request models through the active server roster before
  calling `OnDemandModelLoader`.
- CLI `server session create`, `server session update`, and `server start`
  accept repeated `--model`, `--models`, `--default-model`, and
  `--model-idle-timeout-seconds`.

## Execution Breakdown

- Milestone #1009, #1016, #1023
- Plan #1010: Protocol and gateway config roster schema
  - Unit #1011: Update control-plane protobuf roster contract
  - Unit #1012: Persist gateway roster config and validation
- Plan #1013: OpenAI-compatible payload router
  - Unit #1014: Resolve chat requests by payload model
  - Unit #1015: Reject models outside explicit server roster
- Plan #1017: Model request activity accounting
  - Unit #1018: Track active served model requests
  - Unit #1019: Project server model runtime states
- Plan #1020: Idle sweep unload execution and metrics
  - Unit #1021: Compute served roster idle sweep plans
  - Unit #1022: Execute idle unloads with metrics
- Plan #1024: CLI and operator-state roster UX
  - Unit #1025: Store and render server session rosters
  - Unit #1026: Update server session CLI parser and codec
- Plan #1027: Documentation, pipeline compatibility, and PR evidence
  - Unit #1028: Update plan docs and pipeline examples
  - Unit #1029: Open one evidence-backed PR for all slices

## Metrics

- `control_plane.model_idle_sweep_ms`
- `control_plane.model_idle_unload_count`
- `control_plane.model_idle_skip_active_count`
- `control_plane.model_idle_skip_pinned_count`
- `gateway.model_route_resolution_ms`
- `gateway.model_not_served_count`

## Verification

- Swift protocol generation with `make proto`.
- Focused control-plane tests for gateway config roster persistence, model
  resolver admission, and idle unload behavior.
- Focused CLI tests for `server session create/update`, `server start
  --models`, default model validation, and idle-timeout parsing.
- HTTP gateway tests proving one server can route multiple payload `model`
  values and rejects models outside the roster.
