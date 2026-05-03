# PR-Scoped CI Progress And Restore Probe Fix Plan

## Goal

Keep the PR-scoped performance CI path observable during long probe phases and
prevent the job-registry restore probe from mutating process-global registry
method binding after it runs inside the Python test process.

## Scope

- Preserve the existing `pr-scoped-performance` stage and command progress logs.
- Keep long command-json heartbeat lines compact enough to identify the active
  phase without repeating entire inline probe scripts.
- Fix `scripts/job_registry_restore_probe.py` so it restores
  `ModelOpsJobRegistry._read_manifest_dict` as the original `staticmethod`
  descriptor.
- Add a regression assertion proving the restore probe leaves
  `ModelOpsJobRegistry()._read_manifest_dict(path)` callable after `runpy`
  execution.
- Reduce the synthetic model-registry catalog probe fixture to a stable size
  while preserving the plain-local manifest/stat-elision metric contract.
- Route that command-json probe through the active `uv` environment's `python`
  executable instead of a host `python3` binary.

## Verification

- Focused pytest for the restore probe regression.
- Changed-scope coverage for the touched probe runner/test scope.
- Inspect GitHub Actions logs for `pr-scoped-performance` heartbeat lines when
  confirming remote CI.

## Metrics Report

The changed hot path is CI probe execution hygiene. Runtime performance metrics
are not applicable; coverage and remote Actions progress logs are the evidence.
