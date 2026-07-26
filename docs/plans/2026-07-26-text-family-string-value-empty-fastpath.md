# Text Family String Metadata Empty Fast Path

## Scope

This Python-only performance slice is limited to `_string_value(...)` in
`services/mlx-worker-python/worker/runtime/text_family_adapters.py`. Repeated
text-family resolution queries many optional metadata keys; most are absent on
common runtime metadata payloads.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`text-family-config-copy-elision` in `infra/perf/pr_scoped_probes.json`. The
probe has focused `test_command`, `coverage_command`, and `probe_command`
entries for the text family adapter, focused tests, and
`scripts/text_family_config_probe.py`.

## Plan

1. Preserve existing string metadata semantics for present, whitespace-padded,
   and empty values.
2. Return the default before calling `strip()` when a metadata lookup returns an
   empty or missing value.
3. Add a regression test that proves missing/empty metadata values avoid the
   `strip()` path.
4. Run focused text-family tests, changed-scope coverage, and the registered
   probe locally on Linux before opening the PR.

## Metrics

Local Linux validation must include the registered probe output before and after
the change. GitHub Actions PR-scoped performance remains the merge gate after the
PR is opened.
