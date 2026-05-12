# Release Gates

This directory stores versioned release-gate policy and workflow assets for Melix.

Current assets:

- `phase8-release-gate-policy.json`: deterministic release thresholds for install, benchmark, recovery, training, M9, and observability evidence
- `quantization-release-gate-policy.json`: deterministic thresholds for `q2` through `q8` quantization benchmark evidence

The checked-in `phase8-release-gate-policy.json` also now includes quantization and observability sections so the main release gate can fail closed on quantization regressions, missing evidence validity metrics, production telemetry sampler leakage, or unbounded debug diagnostics queues.

Release gate automation is driven by:

- `scripts/phase8_release_gate.py`
- `scripts/phase8_metrics_report.py`
- `.github/workflows/release-gates.yml`
- `docs/runbooks/phase-8-release-gates.md`
- `docs/runbooks/phase-8-product-acceptance.md`
