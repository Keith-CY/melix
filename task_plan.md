# Task Plan

## Goal

Close `M11.1` by adding an explicit disk-streaming runtime mode, typed session-facing flags, and
operator-visible state so Melix can distinguish memory-resident versus disk-streamed execution
without silent fallback.

## Scope

- extend the authoritative control-plane contract with disk-streaming mode semantics and typed
  runtime flags
- carry the mode through control-plane session state, CLI surfaces, and worker-facing runtime
  settings
- fail unsupported runtime paths explicitly instead of silently ignoring disk-streaming requests

## Measurement Points

- disk-streaming intent must be represented in typed protocol state rather than inferred from free
  form metadata
- control-plane snapshots and operator surfaces must show whether a session is using resident or
  disk-streaming mode
- runtime adapters must reject unsupported disk-streaming requests with deterministic typed errors
  so operators can diagnose why a session did not enter the requested mode

## Phases

1. Protocol and settings contract
   - status: completed
   - evidence:
     - update the control-plane schema and generated outputs so disk-streaming mode is explicit in
       runtime settings and session projection payloads
     - define the exact worker-facing flag mapping and validation rules before broad implementation
2. Control-plane and runtime propagation
   - status: completed
   - evidence:
     - thread the new mode through control-plane state, CLI or operator mutations, and worker
       request shaping
     - ensure unsupported runtimes surface typed failures rather than silently downgrading to
       resident mode
3. Verification and milestone bookkeeping
   - status: completed
   - evidence:
     - run `make proto`, `make swift-test`, and `make py-test` or narrower authoritative commands
       as required by the touched scope
     - record changed-line coverage at or above `95%`, update `progress.md`, and mark `M11.1`
       completed only after protocol, runtime, and operator evidence are captured

## Acceptance

- disk-streaming mode is represented consistently across protocol, control plane, and runtime
  settings
- operator-facing snapshots and CLI output make the selected mode visible without ad-hoc decoding
- unsupported runtime paths fail explicitly with typed disk-streaming validation errors

## Risks

- untyped disk-streaming flags would let different layers disagree about the effective execution
  mode and make future budgeting or cache-policy work harder to reason about
- silently ignoring unsupported disk-streaming requests would create false operator confidence and
  invalidate any later memory-budgeting evidence
- projecting mode only inside worker internals would leave the control plane and desktop shell
  unable to explain why a session is resident versus streamed

## Outcome

- m11_1_disk_streaming_mode_and_runtime_flags_completed
