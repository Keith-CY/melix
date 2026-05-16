# Code eval stdio tail pread slice

## Scope

This Python-only performance slice narrows the code-evaluation stdio tail read path in `worker.engine.code_eval_runner._read_limited_stdio(...)`.

When stdout or stderr exceeds the configured byte limit, the parent process only needs the tail bytes plus the file size. The previous implementation used `fstat()`, `lseek()`, and `read()` for oversized files. This slice uses `os.pread()` when available so the oversized-tail path avoids mutating the file descriptor offset and replaces the seek+read pair with a direct positional read. Platforms without `os.pread()` keep the existing seek/read fallback.

## Registered probe

The affected path is covered by the existing PR-scoped `code-eval-stdio-tail-single-stat` probe in `infra/perf/pr_scoped_probes.json`. This slice keeps the same focused `test_command`, `coverage_command`, and `probe_command` contract, extends the focused tests with pread/fallback assertions, and normalizes the registered probe command to run the checked-in `scripts/code_eval_stdio_probe.py` via `python3`.

## Verification plan

- Run the registered focused pytest command for `code-eval-stdio-tail-single-stat`.
- Run the registered changed-scope coverage command for `code-eval-stdio-tail-single-stat`.
- Run `scripts/code_eval_stdio_probe.py` before and after the change on Linux and compare `elapsed_ms_mean`; `stdio_stat_calls_mean`, tail length, and output-limit guard metrics must remain stable.
- Run the PR-scoped performance runner for `code-eval-stdio-tail-single-stat` before merging.

## Success criteria

- Behavior remains unchanged for missing files, oversized files, directory reads, close errors, and platforms without `os.pread()`.
- Local Linux probe improves or holds steady for `elapsed_ms_mean` without changing output-limit behavior.
- Registered CI probe completes successfully before merge.
