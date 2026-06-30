# Local Job Follow-up JSON Suffix Fast Path

## Context

`LocalJobContinuationStore.scan_followup_candidates()` scans flat local-job record stores and filters record files by the `.json` suffix before loading and reconciling each candidate. The PR-scoped probe `local-job-followup-scan-scandir` covers this path with focused tests, coverage, and a command-json performance probe.

## Slice

Use `str.endswith(".json")` with a local suffix binding during the scandir loop instead of creating a five-character slice for every directory entry. This keeps semantics unchanged:

- only non-symlink regular files with `.json` names are considered;
- `.json.tmp`, lock files, directories, and non-record notes stay ignored;
- sorted job-id ordering remains unchanged;
- the existing special handling for an exact `.json` filename is preserved.

## Verification Plan

- Focused local tests from the registered probe entry.
- Changed-scope coverage command from `infra/perf/pr_scoped_probes.json`.
- Registered local probe command `scripts/local_job_followup_scan_probe.py` on Linux.
- GitHub PR-scoped performance workflow after PR creation.

## Metrics

Baseline Linux probe before the slice, compared against the fresh `origin/main` checkout with `MELIX_LOCAL_JOB_SCAN_RECORDS=500` and `MELIX_LOCAL_JOB_SCAN_SAMPLES=9` across three runs:

- `elapsed_ms_mean` samples: `21.762993`, `20.699737`, `21.088847`
- aggregate baseline mean: `21.183859 ms`
- `scandir_calls_mean=1.0`, `path_glob_calls_mean=0.0`, `path_exists_calls_mean=0.0`

After the slice under the same local settings:

- `elapsed_ms_mean` samples: `17.618416`, `17.841842`, `18.506472`
- aggregate head mean: `17.988910 ms`
- `scandir_calls_mean=1.0`, `path_glob_calls_mean=0.0`, `path_exists_calls_mean=0.0`

Local delta: `-3.194949 ms` mean, about `15.08%` faster on the scan probe. CI remains the registered validation source for PR-scoped comparison.
