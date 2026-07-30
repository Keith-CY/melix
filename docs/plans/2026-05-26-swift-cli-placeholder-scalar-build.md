# Swift CLI metric placeholder scalar build

## Scope

This Swift performance slice keeps CLI JSON envelope behavior unchanged while reducing the temporary allocation cost of metric-placeholder token construction.

## Registered probe

Existing registered probe: `swift-cli-json-envelope-encoding` in `infra/perf/pr_scoped_probes.json`.

The probe covers:

- `Sources/MelixCLICore/MelixCLIJSON.swift`
- `tests/MelixCLITests/MelixCLIRunnerTests.swift`
- `infra/perf/pr_scoped_probes.json` focused command selection

The registry defines focused `test_command`, `coverage_command`, and `probe_command` entries and runs on `macos-15`. Linux cannot validate Swift runtime performance for this slice, so the PR-scoped macOS CI probe is the authoritative performance validation source.

## Optimization

`MelixCLIJSONMetricPatch.makePlaceholder(metricName:)` previously used `String.map` over `Character` values, creating an intermediate array before rebuilding the sanitized metric-name string. This slice builds the sanitized name directly from Unicode scalars into a reserved `String` and reuses a static alphanumeric character set, preserving the same token shape while avoiding the intermediate mapped array.

The 2026-07-14 follow-up keeps the same Swift-only boundary and registered `swift-cli-json-envelope-encoding` probe. The hot CLI envelope metric name is always `melix.cli.json_encode_ms`, so `makePlaceholder(metricName:)` now recognizes that exact metric and builds the already-sanitized token from a cached prefix plus a fresh UUID. Non-default metric names still use the existing scalar sanitizer, preserving Unicode and punctuation behavior.

## Behavior

The placeholder still:

- preserves alphanumeric metric-name scalars;
- replaces non-alphanumeric scalars with `_`;
- wraps the sanitized metric name and UUID with `__MELIX_METRIC_...__`;
- keeps `jsonLiteral` and `jsonLiteralData` synchronized with the token.

## Verification plan

Run any available local static/unit Swift command on the current host. Because this scheduled job runs on Linux and Swift runtime validation is macOS-only for this probe, rely on the registered `swift-cli-json-envelope-encoding` GitHub Actions probe and green PR checks before merge.
