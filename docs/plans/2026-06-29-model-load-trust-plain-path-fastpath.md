# Model Load Trust Plain Path Fast Path

## Scope

This Python-only performance slice is limited to model-load trust policy config
file detection in `services/mlx-worker-python/worker/model_load_trust.py`.

The affected path is already covered by the registered PR-scoped performance
probe `model-load-config-json-bytes` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for the model-load trust tests and inline config JSON
probe, so no probe registry change is required for this slice.

## Optimization

The model-load trust path resolves the `config.json` path on every trust-policy
resolution. Common catalog model paths are already plain `str` values without
leading or trailing whitespace. This slice adds an exact-`str` fast path that
reuses the path directly and only falls back to the existing `str(...).strip()`
normalization for blank, padded, or non-exact values. The behavior remains
unchanged: blank paths, whitespace-normalized paths, tilde expansion, missing
files, non-regular paths, JSON decode errors, non-dict payloads, and custom-loader
`auto_map` detection all keep the existing fallbacks.

## Verification

Run the registered focused local Linux commands from `model-load-config-json-bytes`
in `infra/perf/pr_scoped_probes.json` before opening the PR:

```bash
python3 - <<'PY'
import json, subprocess
from pathlib import Path
probe = next(
    item for item in json.loads(Path("infra/perf/pr_scoped_probes.json").read_text())
    if item["id"] == "model-load-config-json-bytes"
)
for key in ("test_command", "coverage_command", "probe_command"):
    rc = subprocess.run(probe[key], shell=True).returncode
    if rc:
        raise SystemExit(rc)
PY
```

CI PR-scoped performance remains the merge gate for the registered probe result.

## 2026-07-03 follow-up slice: local JSON loads binding

This Python-only follow-up keeps the same registered
`model-load-config-json-bytes` probe and narrows to config JSON parsing in
`_read_model_config_for_stat(...)`. The implementation binds `json.loads` once at
module import time and then hoists that module-local binding into a local variable
inside the cached read helper before parsing bytes from `config.json`. This avoids
the repeated `json.loads` attribute lookup on cache misses while preserving the
existing binary read path, JSON decode fallback, non-dict fallback, stat-keyed
cache behavior, and custom-loader `auto_map` detection semantics.

The affected path remains covered by the existing focused `test_command`,
`coverage_command`, and `probe_command` for `model-load-config-json-bytes` in
`infra/perf/pr_scoped_probes.json`; no registry shape change is required.

## Success Criteria

- Focused model-load trust tests pass.
- Changed-scope coverage for `worker.model_load_trust` stays at or above the repository threshold.
- The registered probe reports a directionally improved config JSON hot path.
- PR-scoped performance CI selects and completes the registered probe before merge.
