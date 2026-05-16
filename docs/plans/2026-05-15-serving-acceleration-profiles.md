# Serving Acceleration Profiles And Effective Config Export

## Goal

Close issue #351 by making serving acceleration profiles a durable Melix operator
contract instead of a loose collection of low-level serving knobs.

## Scope

- Define the initial serving profile identifiers: `balanced`, `throughput`,
  `low-memory`, and `long-session`.
- Resolve profile defaults before manual serving-default overrides.
- Persist the requested profile with server sessions and gateway serving
  defaults.
- Expose requested and effective profile details in CLI JSON state, control-plane
  serving-default summaries, request metadata, diagnostics bundles, and
  benchmark/evidence artifacts.
- Keep advanced low-level fields visible and overrideable.

## Profile Contract

| Profile | Intent | Resolved defaults |
|---|---|---|
| `balanced` | Default serving with current Melix behavior. | `baseline`, no draft model, `num_draft_tokens=0`, concurrent processing on, `max_concurrent_requests=4`, `prefill_batch_size=2`, `completion_batch_size=2` |
| `throughput` | Higher request throughput for batch-like local serving. | `speculative_decode`, draft model required through override, `num_draft_tokens=6`, concurrent processing on, `max_concurrent_requests=8`, `prefill_batch_size=4`, `completion_batch_size=4` |
| `low-memory` | Conservative serving for constrained local memory. | `baseline`, no draft model, `num_draft_tokens=0`, concurrent processing off, `max_concurrent_requests=1`, `prefill_batch_size=1`, `completion_batch_size=1` |
| `long-session` | Repeated-session serving with bounded batching and baseline decode. | `baseline`, no draft model, `num_draft_tokens=0`, concurrent processing on, `max_concurrent_requests=2`, `prefill_batch_size=2`, `completion_batch_size=1` |

`throughput` intentionally does not invent a draft model. It requires the
operator to provide `--draft-model-id` when the resolved profile selects
speculative decode. That preserves capability visibility and avoids silently
claiming acceleration for unsupported target/draft pairings.

## Resolution Model

Resolution order is:

1. built-in profile defaults
2. environment defaults for gateway serving state
3. persisted server-session defaults
4. per-flag CLI overrides
5. model-level serving overrides where the current model settings already own
   precedence

Manual flags preserve the current advanced operator behavior:

- `--acceleration-mode baseline` clears draft model and draft-token settings.
- `--acceleration-mode speculative_decode` requires a draft model from either
  the profile-resolved state or `--draft-model-id`.
- `--draft-model-id` implies speculative decode unless `--acceleration-mode
  baseline` was explicitly requested.
- `--num-draft-tokens` overrides the profile default only when speculative
  decode is active.

## Operator Surfaces

- `melix server session create/update` accepts `--acceleration-profile PROFILE`.
- Server-session JSON includes `acceleration_profile`.
- `melix server snapshot --json` exposes requested/effective profile identifiers
  plus profile-resolved serving fields in `serving_defaults.sessions[]`.
- Worker request metadata includes `melix.gateway.acceleration_profile` so
  request diagnostics can associate events with the selected operator profile.
- Debug bundle `effective-config.json` and capability receipts preserve profile
  details when the source run record contains them.
- Benchmark and benchmark-matrix parameters carry
  `acceleration_profile_id`/`acceleration_profile` through persisted artifacts
  and CSV exports.

## Probes And Metrics

- Control-plane profile resolution is measured by existing serving-defaults
  snapshot tests and the `gateway.serving_defaults_apply_ms` path named in the
  M13.2 plan.
- Request metadata propagation is validated through focused translator tests.
- Benchmark/evidence export overhead is bounded to additional string fields in
  existing run/evidence rows; no new runtime sampler is introduced.

## Verification

- CLI parser/runner tests for profile selection, override precedence, and
  persisted JSON output.
- Control-plane tests for deterministic built-in profile resolution and
  requested/effective summary serialization.
- Request translator tests for `melix.gateway.acceleration_profile`.
- Benchmark export tests proving profile fields are recorded in evidence/CSV
  artifacts.
- `make proto`
- focused Swift tests for touched CLI and control-plane scopes
- `git diff --check`

## Acceptance

- Operators can select a named profile without hand-assembling low-level knobs.
- Low-level overrides remain available and deterministic.
- Effective profile config is visible in CLI/control-plane surfaces and
  persisted artifacts.
- Issue #351 can be closed by a PR with local verification evidence.
