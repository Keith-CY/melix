# Desktop Environment Doctor And Storage Cleanup Plan

## Goal

Define the Melix P4.2 Desktop environment doctor and storage cleanup contract
for the #1511 M4 milestone and #1515 P4.2 plan so packaged-app runtime
diagnostics, proxy and certificate inspection, workspace artifact inventory,
cleanup dry-run, cleanup apply, and cleanup receipts have one shared plan
before #1516 and #1517 implementation work begins.

## Architecture

The Swift control plane remains the authority for operator-visible runtime
state, active jobs, server health, Desktop presentation, and cleanup admission.
The Python worker may collect filesystem and environment evidence only through
bounded request/receipt paths owned by the control plane or model-ops boundary.
Desktop and CLI must consume the same machine-readable diagnostic, inventory,
and cleanup receipts; they must not infer environment health or safe-delete
state from ad hoc shell output, raw logs, or local file existence.

P4.2 is split into one plan issue and two executable unit issues:

- #1515 / P4.2 defines the environment diagnostic, storage inventory, cleanup
  plan, receipt, redaction, active-job protection, and metrics contracts.
- #1516 / U4.2.1 adds GUI shell PATH, proxy, certificate, runtime binary, and
  local server diagnostics.
- #1517 / U4.2.2 adds storage inventory plus dry-run/apply cleanup plans and
  receipts.

The first implementation slice should prove the receipt model with existing
Melix home, runtime directory, install manifest, server health, and workspace
artifact paths before adding broad source-specific repairs. Safe cleanup must
start with dry-run byte accounting, then add apply mode only after active-job
protection is measurable.

## Existing Anchors

- `docs/reference-scans/m-courtyard-lessons.md` identifies app-managed
  environment setup, Finder-launched PATH recovery, proxy and certificate
  support, and storage cleanup as the M4 improvement direction.
- `docs/plans/2026-05-24-m-courtyard-improvement-roadmap.md` maps #1511
  through #1517 into the M4 milestone, plan, and unit hierarchy.
- `docs/plans/2026-06-24-cross-runtime-model-inventory.md` defines the P4.1
  source descriptor, scan receipt, redaction, and performance-probe model that
  P4.2 must preserve for external model stores.
- `docs/runbooks/phase-8-local-install.md` defines packaged install
  environment exports, launch-agent logs, update-check diagnostics, and current
  install artifact locations.
- `docs/workspace-manifest-contract.md` defines workspace artifact types for
  raw inputs, prepared datasets, adapters, logs, exports, reports, and evidence
  bundles.
- `docs/evidence-telemetry-report-contract.md` defines evidence redaction,
  diagnostics bundle boundaries, and bounded local artifact reporting.
- `services/control-plane-swift` owns server-session state, route readiness,
  local HTTP health, Desktop state hydration, and active workflow/job state.
- `services/mlx-worker-python` owns worker-side model operations, filesystem
  model registry scanning, export artifact layout slices, and Python runtime
  dependency execution.

## Non-Goals

- Do not copy code, assets, or implementation structure from the reference
  project.
- Do not print secrets, raw proxy credentials, certificate contents, private
  token values, private repository URLs with embedded credentials, or full
  unredacted host paths in public logs, Desktop, CLI, HTTP responses, or PR
  evidence.
- Do not make Desktop or CLI run independent shell probes whose result shape
  differs from the shared diagnostic receipt.
- Do not delete files in the diagnostic unit. Environment diagnosis may propose
  remedies but cleanup belongs to #1517.
- Do not delete active training, export, benchmark, evaluation, server-session,
  model-download, or workspace-preflight artifacts.
- Do not clean external read-only runtime stores from P4.1 unless a later
  explicit plan changes the ownership policy.
- Do not treat a dry-run cleanup plan as evidence that files were deleted.
- Do not add automatic repair, dependency installation, model download,
  network mutation, or certificate trust-store mutation in P4.2.

## Diagnostic Receipt Contract

Every environment diagnostic run writes a receipt with schema
`melix.desktop_environment_diagnostic_receipt.v1`. The first implementation may
return this receipt through existing CLI/Desktop JSON paths. If the receipt
becomes a long-lived worker or control-plane API, the relevant protobuf schema
must be updated and generated artifacts committed in the same unit.

Required top-level fields:

- `schema_version`
- `diagnostic_id`
- `started_at_unix_ms`
- `completed_at_unix_ms`
- `invocation_context`
- `checks`
- `summary`
- `redaction_summary`
- `metrics`

Each diagnostic check must include:

- `check_id`
- `check_kind`
- `display_name`
- `status`
- `severity`
- `observed`
- `expected`
- `remediation`
- `evidence`
- `redaction_count`
- `latency_ms`

Required `check_kind` values for #1516:

- `shell_path`
- `runtime_binary`
- `python_version`
- `uv_version`
- `mlx_version`
- `proxy_environment`
- `certificate_environment`
- `melix_home`
- `runtime_directory`
- `local_server_health`

`status` is one of `pass`, `warn`, `fail`, `skipped`, or `unknown`. `severity`
is one of `info`, `actionable`, `blocking`, or `internal_error`. A check with
redacted evidence may still pass, but it must increment `redaction_count` and
record the redaction policy used.

## Diagnostic Matrix

### Shell PATH

- Inputs: process `PATH`, login-shell PATH candidates when available, packaged
  install environment exports, and configured runtime binary roots.
- Pass condition: required runtime binaries can be resolved from the effective
  Desktop/CLI environment without relying on interactive shell-only state.
- Failure modes: `missing_path_entry`, `finder_launch_path_gap`,
  `binary_not_found`, `path_not_readable`, `path_probe_timed_out`.
- Redaction: absolute path display keeps stable labels, basename, and digest;
  home-relative paths may be shown only after credential-like segments are
  redacted.

### Runtime Binaries

- Inputs: configured `uv`, Python, Melix worker, optional `mlx-lm`, and local
  runtime binary paths.
- Pass condition: binary exists, is executable, and reports a bounded version
  or capability string when the probe supports it.
- Failure modes: `not_found`, `not_executable`, `version_probe_failed`,
  `unsupported_version`, `probe_timed_out`.
- Redaction: raw command arguments and host paths are redacted before public
  receipt emission.

### Python, uv, And MLX Versions

- Inputs: effective Python interpreter, `uv` project environment, locked
  worker dependency metadata, and MLX import/version probes.
- Pass condition: the interpreter and dependency set are compatible with the
  locked worker project and the selected runtime path.
- Failure modes: `python_missing`, `python_unsupported`, `uv_missing`,
  `dependency_environment_mismatch`, `mlx_missing`, `mlx_version_mismatch`,
  `import_failed`.
- Redaction: traceback details are summarized; environment variables and local
  paths are redacted.

### Proxy And Certificate Environment

- Inputs: `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`, certificate
  bundle variables, Melix settings, and packaged install environment exports.
- Pass condition: proxy and certificate settings are internally consistent and
  can be passed to worker/runtime commands without exposing secrets.
- Failure modes: `proxy_url_invalid`, `proxy_credentials_redacted`,
  `certificate_path_missing`, `certificate_path_unreadable`,
  `conflicting_proxy_settings`, `certificate_probe_timed_out`.
- Redaction: userinfo, tokens, passwords, query secrets, and raw certificate
  contents are never emitted. Certificate paths are path-redacted and digest
  referenced.

### Local Server Health

- Inputs: current control-plane server-session state, configured local HTTP
  port, authenticated health endpoint result, and route-readiness summary.
- Pass condition: server-session health and route readiness agree with the
  operator-visible Desktop state.
- Failure modes: `server_not_running`, `port_conflict`, `health_unreachable`,
  `health_auth_failed`, `route_not_ready`, `health_probe_timed_out`.
- Redaction: health payloads are filtered to typed status, route counts,
  latency, and known diagnostic fields.

## Storage Inventory Contract

Every storage inventory writes a receipt with schema
`melix.storage_inventory_receipt.v1`.

Required top-level fields:

- `schema_version`
- `inventory_id`
- `started_at_unix_ms`
- `completed_at_unix_ms`
- `workspace_roots`
- `artifact_roots`
- `artifact_entries`
- `summary`
- `redaction_summary`
- `active_artifact_summary`
- `metrics`

Each artifact entry must include:

- `artifact_id`
- `artifact_kind`
- `root_kind`
- `path_redaction`
- `path_digest`
- `byte_size`
- `mtime_unix_ms`
- `retention_class`
- `ownership`
- `active_protection`
- `cleanup_eligibility`
- `cleanup_reason`

Required `artifact_kind` values for #1517:

- `raw_file`
- `cleaned_segment`
- `dataset_version`
- `checkpoint`
- `adapter_output`
- `export_intermediate`
- `runtime_log`
- `stale_temp_file`
- `evidence_bundle`

`ownership` is one of `melix_owned`, `workspace_owned`, or
`external_read_only`. `cleanup_eligibility` is one of `retain`, `cleanable`,
`protected_active`, `blocked_external`, `blocked_unknown`, or `missing`.
External read-only roots inherited from P4.1 are always `blocked_external`
unless a later governing cleanup plan changes their ownership.

## Cleanup Plan And Receipt Contract

Cleanup dry-run and apply share one plan shape with schema
`melix.storage_cleanup_plan.v1`. Apply writes a terminal receipt with schema
`melix.storage_cleanup_receipt.v1`.

Required cleanup plan fields:

- `schema_version`
- `cleanup_plan_id`
- `inventory_id`
- `mode`
- `generated_at_unix_ms`
- `retained_entries`
- `cleanable_entries`
- `protected_entries`
- `blocked_entries`
- `summary`
- `metrics`

`mode` is `dry_run` or `apply`. Dry-run never deletes files. Apply may delete
only entries that were `cleanable` in a same-run inventory and remained
unchanged by path digest, mtime, byte size, and active protection state.

Apply receipts must include:

- `cleanup_receipt_id`
- `cleanup_plan_id`
- `started_at_unix_ms`
- `completed_at_unix_ms`
- `deleted_entries`
- `retained_entries`
- `protected_entries`
- `failed_entries`
- `summary`
- `metrics`

Active-job protection must be checked immediately before each delete. If a file
becomes active, changes size, changes mtime, changes digest, or moves between
dry-run and apply, the apply receipt records `protected_active` or
`changed_since_plan` and retains it.

## Desktop And CLI Contract

CLI and Desktop present the same receipt shapes:

- CLI may render a table and write JSON, but the JSON is the source of truth.
- Desktop may summarize checks, inventory, and cleanup decisions, but it reads
  from the same receipt fields and must not re-run probes independently.
- Both surfaces show redacted path labels, byte summaries, active protection
  counts, and remediation text from the receipt.
- Both surfaces link operator-private evidence only when the evidence path is
  Melix-owned and redacted in the public summary.

## Redaction And Source-Of-Truth Rules

- Redact values before writing logs, Desktop summaries, CLI output, HTTP
  responses, PR evidence, or issue comments.
- Preserve secret provenance with counts and digest references, not raw values.
- Keep full unredacted local paths only in explicitly operator-private,
  Melix-owned evidence files when required for local troubleshooting.
- Never duplicate environment diagnostic logic between Desktop and CLI.
- Never infer cleanup eligibility from UI state; use the inventory receipt and
  control-plane active-job state.
- Never let cleanup mutate P4.1 `external_read_only` source roots.

## Metrics And Probes

The P4.2 implementation units must define PR-scoped probes before code changes
that alter diagnostic, inventory, or cleanup paths.

Required diagnostic metrics:

- `diagnostic_latency_ms`
- `path_candidate_count`
- `runtime_binary_probe_latency_ms`
- `version_probe_latency_ms`
- `proxy_check_latency_ms`
- `certificate_check_latency_ms`
- `local_server_health_latency_ms`
- `redaction_count`
- `diagnostic_failure_count`

Required storage and cleanup metrics:

- `storage_inventory_latency_ms`
- `inventory_artifact_count`
- `inventory_byte_size`
- `retained_byte_size`
- `cleanable_byte_size`
- `protected_active_artifact_count`
- `cleanup_dry_run_latency_ms`
- `cleanup_apply_latency_ms`
- `safe_delete_count`
- `deleted_byte_size`
- `cleanup_failure_count`

Probe success criteria:

- Finder-style constrained PATH fixtures must produce an actionable diagnostic
  without exposing secrets.
- Proxy and certificate fixtures with credentials must produce nonzero
  redaction counts and no raw credential strings.
- Storage inventory latency must stay within the configured fixture budget.
- Dry-run must never delete files and must report retained, cleanable,
  protected, and blocked bytes.
- Apply must delete only unchanged cleanable Melix-owned artifacts and must
  protect active or changed artifacts.
- Desktop and CLI fixture outputs must agree on summary counts and receipt IDs.

## #1516 Implementation Notes

The #1516 implementation emits the shared environment diagnostic receipt through
existing `melix doctor --json`, `melix system --json`, and debug bundle JSON
paths before introducing a new long-lived protobuf API. The receipt is built in
shared Swift diagnostics code so CLI and Desktop decode the same fields. Debug
bundles write the receipt both as `environment-diagnostic.json` and as the
manifest summary payload.

`melix doctor --json` and `melix system --json` intentionally expose
`environment_diagnostic` as a top-level field. `doctor --json` also preserves
the nested `system.environment_diagnostic` value inherited from the shared
system payload. The top-level field is the stable convenience path for Desktop
and CLI automation; the nested copy remains part of the system payload shape.

The first slice keeps version and local-server probes bounded to the effective
process environment. It records executable resolution and health-probe
availability without spawning dependency imports or opening network
connections, so Finder-style PATH and redaction failures are visible without
turning diagnostics into a long-running runtime probe.

## Verification

This #1511/#1515 change is documentation-only. The PR that introduces this
plan should run:

```bash
git diff --check
python3 scripts/validate_pr_evidence.py --body-file .runtime/pr-body-issue-1511.md
```

The changed scope has no executable code and no measurable runtime coverage.
Metrics report: `N/A - documentation-only P4.2 readiness plan; #1516 and
#1517 define and run the diagnostic, storage inventory, cleanup dry-run, cleanup
apply, redaction, and performance probes before implementation commits.`

## Acceptance Criteria

- The plan defines the shared Desktop/CLI diagnostic receipt for PATH, runtime
  binaries, Python, uv, MLX, proxy, certificate, Melix home, runtime directory,
  and local server health checks.
- The plan defines storage inventory coverage for raw files, cleaned segments,
  dataset versions, checkpoints, adapter outputs, export intermediates, runtime
  logs, stale temp files, and evidence bundles.
- The plan defines cleanup dry-run and apply receipt semantics, including
  active-job protection and changed-since-plan protection.
- The plan records redaction, source-of-truth, and external-read-only cleanup
  boundaries.
- The plan records implementation metrics and PR-scoped probe expectations for
  #1516 and #1517.
- The P4.2 roadmap entry links this detailed plan so child issues share one
  contract.

## Rollback Or Safe Exit

- If #1516 proves that a diagnostic check cannot be represented without a
  source-specific side channel, update this plan before implementing the
  divergent shape.
- If #1517 cannot protect an artifact class with current active-job state, keep
  that class retained and file a follow-up instead of deleting optimistically.
- If diagnostic or cleanup probes show a regression, fix the implementation
  before opening the child PR or record an explicit, reviewed performance
  tradeoff in that child PR.
