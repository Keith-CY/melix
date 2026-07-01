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

## Success Criteria

- Focused model-load trust tests pass.
- Changed-scope coverage for `worker.model_load_trust` stays at or above the repository threshold.
- The registered probe reports a directionally improved config JSON hot path.
- PR-scoped performance CI selects and completes the registered probe before merge.
