# Melix CI Failure Remediation Plan

## Scope

This plan remediates the failing GitHub Actions checks currently blocking PR validation for the
`ci-github-actions-hardening` branch.

The slice is intentionally narrow:

- restore `ci-pr` workflow reliability
- harden the PR-only validation and packaging workflows after self-review findings
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
- `actionlint-and-diffcheck` currently runs `git diff --check` against a clean checkout, which does
  not validate the proposed PR patch and misses whitespace or conflict-marker defects introduced by
  the reviewed change.
- `proto-drift` installs `protobuf` and `swift-protobuf` directly from Homebrew on every run, so
  the protocol generators can drift independently of the repository's locked Python and Swift
  dependency graph.
- `python-tests` execute the sandboxed evaluator via the framework wrapper interpreter on GitHub
  macOS runners, which fails under `sandbox-exec` before the evaluation payload is emitted.
- `integration-tests` run before the required Swift products are built, so the suite fails on
  missing `melix-control-plane` and `melix-text-worker-swift` executables.
- `integration-tests` also need a larger timeout budget once the required Swift prerequisite build
  runs in the same job on GitHub macOS runners.
- `swift-tests` invoke Python bridge fixture processes through `uv run`, but the workflow does not
  provision Python or `uv`, so worker-client bridge tests fail even when the Swift code is valid.
- `package-app` fails under Xcode 16.4 concurrency checks because a cached `NSImage` static
  property is not isolated to the main actor.
- `swift-tests` expose a timing-sensitive request coordinator test that assumes disconnect-grace
  expiry has already completed after a fixed sleep.
- `validate_pr_evidence.py` currently accepts empty fenced code blocks and loose placeholder text
  such as `TODO: fill later`, which weakens the mandatory PR evidence gate.
- `validate_pr_evidence.py` also accepts the shipped `Commands Run` placeholder comment inside a
  fenced block, so a template-only PR body can still pass validation.
- `package-self-contained-app` grants `contents: write` for the full workflow even though only the
  tag-release attachment path needs repository write access.
- the release-gate evaluation policy now requires `eval.<suite>.typed_score_mean`, but legacy
  evidence producers and fixtures still emit `eval.<suite>.accuracy`, so the gate currently fails
  valid historical evidence during the metric migration.
- the scheduled and push-triggered `release-gates` runs on `main` currently share the same
  concurrency key and can cancel each other.
- the release attachment job references `softprops/action-gh-release` by mutable tag instead of an
  immutable commit SHA.
- the root Dependabot `pip` entry duplicates the worker Python ecosystem even though the workspace
  root has no direct Python dependencies.
- `ci-pr` still runs the full `integration-tests` job for docs-only pull requests because the job
  has no change-scope gate.
- the packaging workflow relies on generated GitHub release notes by design, but that assumption is
  not documented near the write-scoped release action.

## Planned Changes

### Workflow fixes

- Pin `actionlint` to a resolvable published version.
- Make the diff check validate the checked-out merge patch rather than the empty worktree state.
- Update the integration workflow path so Swift artifacts are built before `make integration-test`.
- Increase the integration workflow timeout so the prerequisite build and full Python suite can both
  complete on GitHub macOS runners.
- Provision Python, `uv`, and the locked worker environment before running `make swift-test`.
- Move protocol generation to repository-pinned toolchains so `proto-drift` is deterministic across
  runs.
- Reduce packaging workflow permissions to `contents: read` by default and isolate release-asset
  publication in a tag-only write-scoped job.
- Separate scheduled and push-triggered release-gate workflow concurrency keys on `main`.
- Pin the release-attachment action to an immutable commit SHA.
- Drop the redundant root Dependabot `pip` updater so the worker remains the single Python package
  update surface.
- Gate `integration-tests` behind a PR diff scope check so docs-only pull requests skip the 18-minute
  integration suite while merge-queue runs still execute it unconditionally.
- Document that tag pushes are the source of truth for release body generation in the packaging
  workflow so `generate_release_notes: true` is an explicit policy choice rather than an implicit
  default.

### Python sandbox execution

- Prefer the direct Python launcher inside `Python.app` when present, instead of invoking the
  framework wrapper binary under sandboxing.
- Add regression coverage for the executable-selection behavior so the runner-specific path stays
  stable.
- Tighten PR evidence parsing so empty fenced blocks and placeholder-prefixed bullets fail
  validation.
- Ignore placeholder comment lines inside fenced `Commands Run` blocks so the shipped template text
  cannot satisfy the evidence gate by itself.
- Normalize release-gate evaluation evidence so both `eval.<suite>.accuracy` and
  `eval.<suite>.typed_score_mean` remain accepted during the metric migration, while keeping the
  canonical `typed_score_mean` output.

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
- Integration workflow budget: the combined prerequisite build and test duration stays within the
  configured CI timeout window.
- Swift worker bridge fixture execution: `uv`-backed bridge commands remain dispatchable inside the
  Swift test job.
- Disconnect-grace test determinism: terminal failure metrics are observed before assertions run.
- PR evidence gate strength: required sections reject empty code fences and placeholder-prefixed
  items while still accepting justified `N/A:` coverage statements.
- Release-gate metric migration: canonical and legacy evaluation metric names both satisfy the
  gate during the transition period, and the deterministic smoke fixture remains green.
- Protocol generation determinism: the same repository-locked protobuf toolchain is used in CI and
  local regeneration paths.
- Packaging workflow permissions: pull request execution paths stay read-only.
- Workflow scheduling isolation: scheduled and push-triggered release-gate runs do not cancel each
  other on `main`.
- Supply-chain hardening: write-scoped release publication uses an immutable action revision.
- Pull-request CI scope control: docs-only pull requests skip the integration suite, while
  merge-group validation continues to run the full integration path.

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
uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_validate_pr_evidence.py -q
xcrun swift test --package-path services/control-plane-swift --filter "HTTPGatewayTests.RequestCoordinatorTests/disconnectGraceExpiryAbortsTheWorkerAndRecordsATerminalLifecycleFailure()"
xcrun swift test --package-path apps/macos-menubar
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python python -m grpc_tools.protoc --version
HOME="$PWD/.swift-home/protocol" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex/protocol" xcrun swift build --package-path packages/protocol/swift --product protoc-gen-swift --disable-automatic-resolution
HOME="$PWD/.swift-home/protocol" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex/protocol" xcrun swift build --package-path packages/protocol/swift --product protoc-gen-grpc-swift-2 --disable-automatic-resolution
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
- integration CI has enough timeout headroom for the prerequisite Swift build plus the full suite
- swift test CI provisions the Python bridge runtime dependencies before worker-client tests launch
- sandboxed Python code evaluation succeeds on runner-compatible interpreter paths
- the menu bar app package builds under the current Xcode concurrency checks
- the request coordinator disconnect-grace test no longer depends on a fixed sleep race
