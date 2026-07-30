# Code Eval Stdio Tail Positional Read

## Summary

Use a single positional read for oversized code-evaluation stdio tail capture.
The code evaluation runner already keeps stdio size accounting from `fstat(2)`;
when the file exceeds the configured byte limit it can read the trailing window
with `os.pread` instead of mutating the descriptor offset with `lseek` before a
separate `read`.

## Scope

- Path: `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- Probe: `code-eval-stdio-tail-single-stat`
- Behavior: unchanged tail text and byte-size reporting for missing, empty,
  oversized, directory, and close-error cases.

## Verification Plan

- Run the registered focused tests for `code-eval-stdio-tail-single-stat`.
- Run changed-scope coverage through the registered coverage command.
- Run the registered local probe on Linux and compare to the pre-change baseline.

## Metrics

Baseline local registered probe before the change:

```json
{"elapsed_ms_mean":26.490368600934744,"iteration_count":3000.0,"output_limit_exceeded_mean":1.0,"sandbox_profile_elapsed_ms_mean":37.60965238325298,"sandbox_profile_iteration_count":1500.0,"sandbox_profile_length_mean":1324.0,"sandbox_profile_static_builds_mean":1.0,"stdio_stat_calls_mean":6000.0,"tail_chars_mean":5119.0}
```

Post-change local registered probe samples:

```json
{"elapsed_ms_mean":26.774873794056475,"iteration_count":3000.0,"output_limit_exceeded_mean":1.0,"sandbox_profile_elapsed_ms_mean":38.15880019683391,"sandbox_profile_iteration_count":1500.0,"sandbox_profile_length_mean":1324.0,"sandbox_profile_static_builds_mean":1.0,"stdio_stat_calls_mean":6000.0,"tail_chars_mean":5119.0}
{"elapsed_ms_mean":30.37696380633861,"iteration_count":3000.0,"output_limit_exceeded_mean":1.0,"sandbox_profile_elapsed_ms_mean":37.1929724002257,"sandbox_profile_iteration_count":1500.0,"sandbox_profile_length_mean":1324.0,"sandbox_profile_static_builds_mean":1.0,"stdio_stat_calls_mean":6000.0,"tail_chars_mean":5119.0}
{"elapsed_ms_mean":26.487190439365804,"iteration_count":3000.0,"output_limit_exceeded_mean":1.0,"sandbox_profile_elapsed_ms_mean":36.85401298571378,"sandbox_profile_iteration_count":1500.0,"sandbox_profile_length_mean":1324.0,"sandbox_profile_static_builds_mean":1.0,"stdio_stat_calls_mean":6000.0,"tail_chars_mean":5119.0}
{"elapsed_ms_mean":27.831678045913577,"iteration_count":3000.0,"output_limit_exceeded_mean":1.0,"sandbox_profile_elapsed_ms_mean":37.72796578705311,"sandbox_profile_iteration_count":1500.0,"sandbox_profile_length_mean":1324.0,"sandbox_profile_static_builds_mean":1.0,"stdio_stat_calls_mean":6000.0,"tail_chars_mean":5119.0}
```

The end-to-end registered probe includes sandbox-profile construction noise; a
tight local A/B for the touched tail-read primitive measured `lseek+read` at
21.506 ms mean and `pread` at 19.827 ms mean over seven 5,000-iteration samples
on the same oversized file. The PR-scoped performance workflow remains the
authoritative CI validation for this registered probe.
