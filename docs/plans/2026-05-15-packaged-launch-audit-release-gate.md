# Packaged Launch Audit Release Gate Slice

## Goal

Close the next executable slice from issue #58 by making packaged launch evidence
prove local addressing, health-probe reuse, and installed-app audit completion
through the Phase 8 release gate.

## Scope

- Resolve bind-all HTTP hosts such as `0.0.0.0` to a loopback connect host for
  local launch integrations.
- Include the requested bind host, resolved connect host, health URL, and service
  base URL in packaged and local-install manifests.
- Add release-gate evidence for `installed_app_audit`, `runtime_source`,
  `health_probe_reuse`, and `connect_host_resolution`.
- Fail the release gate when packaged launch evidence is missing, does not use a
  loopback connect host for bind-all launches, does not prove health-client reuse,
  or does not record installed-app audit completion.

## Out Of Scope

- Changing development-mode fallback behavior.
- Running a heavyweight packaged app or importing the full ML runtime in the
  release gate.
- Redesigning packaging target manifests beyond the local addressing and audit
  fields needed by this slice.

## Performance Probes And Metrics

- `packaged_launch.health_probe_reused_client_count` proves the smoke reused one
  health client instead of creating a new client per poll.
- `packaged_launch.time_wait_socket_count` keeps the steady-state local socket
  leak budget below five.
- `packaged_launch.connect_host_loopback` proves a bind-all launch exposes a
  loopback connect host to local integrations.
- `packaged_launch.installed_app_audit_passed` proves release evidence contains
  an installed-app completion audit.

## Verification

- Focused Python tests for local install manifests, macOS app bundle metadata,
  and release-gate evaluation.
- Changed-scope coverage for the touched Python files.
- `git diff --check`.
