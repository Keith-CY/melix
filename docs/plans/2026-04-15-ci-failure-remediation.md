# Melix CI Failure Remediation Plan

## Scope

This plan remediates the failing GitHub Actions checks currently blocking PR validation for the
`ci-github-actions-hardening` branch.

The slice is intentionally narrow:

- restore `ci-pr` workflow reliability
- restore macOS packaging compatibility with the current GitHub runner image and Xcode toolchain
- keep fixes limited to the failing workflow, Python sandbox execution path, and Swift request and
  branding code that the workflows exercise

This slice does not add:

- new CI jobs or matrix expansion
- non-blocking workflow modernization beyond the failing checks
- unrelated runtime behavior changes outside the failing code paths

## Root Causes

- `actionlint-and-diffcheck` references `rhysd/actionlint@v1`, which is not a resolvable GitHub
  Action version.
- `python-tests` execute the sandboxed evaluator via the framework wrapper interpreter on GitHub
  macOS runners, which fails under `sandbox-exec` before the evaluation payload is emitted.
- `integration-tests` run before the required Swift products are built, so the suite fails on
  missing `melix-control-plane` and `melix-text-worker-swift` executables.
- `package-app` fails under Xcode 16.4 concurrency checks because a cached `NSImage` static
  property is not isolated to the main actor.
- `swift-tests` expose a timing-sensitive request coordinator test that assumes disconnect-grace
  expiry has already completed after a fixed sleep.

## Planned Changes

### Workflow fixes

- Pin `actionlint` to a resolvable published version.
- Update the integration workflow path so Swift artifacts are built before `make integration-test`.

### Python sandbox execution

- Prefer the direct Python launcher inside `Python.app` when present, instead of invoking the
  framework wrapper binary under sandboxing.
- Add regression coverage for the executable-selection behavior so the runner-specific path stays
  stable.

### Swift compatibility and determinism

- Isolate tray-icon caching behind the main actor so AppKit image state satisfies current Swift
  concurrency checks.
- Make the disconnect-grace expiry test wait on the terminal signal rather than rely on a fixed
  timing window.

## Performance Probes And Metrics

Measurement points for this remediation:

- Python sandbox regression: evaluator completes and emits its payload under the selected
  interpreter path.
- Integration workflow preparation: required Swift binaries exist before integration tests launch.
- Disconnect-grace test determinism: terminal failure metrics are observed before assertions run.

Success targets:

- all previously failing checks have a concrete local verification command
- touched measurable code paths remain at or above 95 percent automated coverage where the tooling
  supports measurement
- changed-scope metrics report is included in the handoff, with `N/A` explicitly called out for
  workflow YAML where coverage is not meaningful

## Verification Plan

Targeted verification:

```bash
uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_code_eval_runner.py -q
xcrun swift test --package-path services/control-plane-swift --filter "HTTPGatewayTests.RequestCoordinatorTests/disconnectGraceExpiryAbortsTheWorkerAndRecordsATerminalLifecycleFailure()"
xcrun swift test --package-path apps/macos-menubar
```

Broader regression checks:

```bash
make py-test
make swift-test
```

Workflow sanity checks:

```bash
gh workflow view ci-pr --yaml
gh workflow view package-self-contained-app --yaml
```

## Exit Conditions

This remediation is complete when:

- the workflow definitions no longer contain the invalid `actionlint` reference
- integration CI provisions the Swift binaries it depends on before running the Python suite
- sandboxed Python code evaluation succeeds on runner-compatible interpreter paths
- the menu bar app package builds under the current Xcode concurrency checks
- the request coordinator disconnect-grace test no longer depends on a fixed sleep race
