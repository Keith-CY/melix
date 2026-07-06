# Video URI public authority inline fast path

This Python-only performance slice targets repeated URI-backed video preprocessing in `services/mlx-worker-python/worker/runtime/video_preprocessing.py`.

## Scope

- `services/mlx-worker-python/worker/runtime/video_preprocessing.py`
- `services/mlx-worker-python/tests/test_video_preprocessing.py`
- Registered probe: `video-preprocessing-uri-byte-length-reuse`

## Registered probe coverage

The affected path is covered by the existing PR-scoped registered probe `video-preprocessing-uri-byte-length-reuse` in `infra/perf/pr_scoped_probes.json`. The probe entry already defines focused `test_command`, `coverage_command`, and `probe_command` values and watches the video preprocessing source, focused tests, PR-scoped performance selection tests, and `scripts/video_preprocessing_uri_probe.py`.

## Optimization

The common HTTPS public-host validation path now performs the plain-authority checks inline in `_validate_parsed_video_uri()`. This avoids an extra helper call for repeated public remote video references while preserving the slower non-plain parser for localhost, IP-literal, credential, and port-bearing authorities.

## Behavior parity

- Local paths and `file:` references remain accepted.
- HTTPS references without a host remain rejected.
- Public DNS-style hosts remain accepted on the fast path.
- Localhost/private-host/IP-literal validation remains delegated to `_validate_non_plain_remote_video_reference()`.

## Verification plan

1. Run the focused video preprocessing tests and registered PR-scoped probe selection tests from the registry `test_command`.
2. Run the registered changed-scope coverage command.
3. Run the registered `video_preprocessing_uri_probe.py` probe locally on Linux and compare against the pre-change baseline.
4. Use the PR-scoped performance workflow as the merge gate.
