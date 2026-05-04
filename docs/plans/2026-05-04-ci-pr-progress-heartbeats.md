# CI PR Progress Heartbeats

## Goal

Keep the `ci-pr` GitHub Actions workflow observable while long dependency,
Swift build, Python test, and integration phases run without producing normal
test output.

## Scope

- Add a repository-owned command wrapper that emits compact progress lines at a
  fixed interval while preserving the wrapped command's exit status.
- Route long `ci-pr` steps through the wrapper:
  - bootstrap
  - protocol drift check
  - Swift tests
  - Python tests
  - Swift integration prerequisite build
  - integration tests
- Add a shell syntax check for the wrapper in the existing CI lint job.

Out of scope:

- changing the test matrix
- changing timeout budgets
- changing the commands executed by `make`

## Metrics And Success Targets

- Every wrapped long CI step emits `[melix-ci] <stage> started`.
- A silent wrapped command emits `[melix-ci] <stage> still running after Ns` at
  the configured interval.
- The wrapper emits `[melix-ci] <stage> completed rc=<code> elapsed=Ns` and
  exits with the same status as the wrapped command.
- `ci-pr` logs should show at least one heartbeat for any silent stage that runs
  longer than `MELIX_CI_PROGRESS_INTERVAL_SECONDS`.

## Verification

- `bash -n scripts/ci_progress.sh`
- local smoke for a successful silent command with a short heartbeat interval
- local smoke for a failing command preserving the non-zero exit status
- `git diff --check`
