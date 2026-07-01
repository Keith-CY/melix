# Export Retention Delete Decision Membership Fast Path

## Scope

This Python-only performance slice is limited to export target retention cleanup
membership checks in `services/mlx-worker-python/worker/productization/export_target_layout.py`.

The affected path is already covered by the registered PR-scoped performance
probe `runtime-export-layout-retention` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for the export layout retention tests and probe, so no
probe registry change is required for this slice.

## Optimization

`build_export_retention_report()` and `_decide_file()` previously allocated two-item
set literals while classifying cleanup-eligible decisions. This slice hoists the
cleanup-delete decision set into a module-level `frozenset` and reuses it for
membership checks.

Behavior remains unchanged: only cleanable and TTL-expired runtime-log decisions
are unlinked when cleanup is enabled, retained files remain retained, missing
files remain non-deleted, and report payload fields keep the same semantics.

## Verification

Run the registered focused local Linux commands from
`runtime-export-layout-retention` in `infra/perf/pr_scoped_probes.json` before
opening the PR:

```bash
python3 - <<'PY'
import json, subprocess
from pathlib import Path
probe = next(
    item for item in json.loads(Path("infra/perf/pr_scoped_probes.json").read_text())
    if item["id"] == "runtime-export-layout-retention"
)
for key in ("test_command", "coverage_command", "probe_command"):
    rc = subprocess.run(probe[key], shell=True).returncode
    if rc:
        raise SystemExit(rc)
PY
```

CI PR-scoped performance remains the merge gate for the registered probe result.

## Success Criteria

- Focused export target layout retention tests pass.
- Changed-scope coverage for `worker.productization.export_target_layout` stays at or above the repository threshold.
- The registered probe reports a directionally improved layout-retention hot path.
- PR-scoped performance CI selects and completes the registered probe before merge.
