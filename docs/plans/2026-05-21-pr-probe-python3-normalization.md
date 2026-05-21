# PR-scoped probe Python 3 command normalization

## Summary

This probe-registration slice keeps Melix PR-scoped performance probes executable in Linux automation that does not provide a bare `python` binary.

## Motivation

The scheduled optimization workflow and repository automation require `python3` instead of `python`. Several registered `command_json` probe fallbacks and file-backed script invocations still used `python`, so a selected probe could fail before it emitted metrics on runners without a `python` alias.

## Scope

- Normalize registered PR-scoped probe commands in `infra/perf/pr_scoped_probes.json` from bare `python` to `python3`.
- Add registry coverage in `test_registered_probes_expose_focused_commands` so future probe entries do not reintroduce bare `python` script or heredoc invocations.
- No optimization behavior changes are included in this slice.

## Validation Plan

- Run the focused PR-scoped performance registry test locally on Linux.
- Run changed-scope coverage for the registry and test change.
- Run representative registered probes after normalization to confirm JSON metrics still emit.
- Use GitHub Actions / PR-scoped performance workflow as the merge gate.

## Metrics Boundary

This is a CI/probe-registration hardening slice, so performance delta is intentionally N/A. It unlocks reliable registered probe validation for later Python and Swift slices.
