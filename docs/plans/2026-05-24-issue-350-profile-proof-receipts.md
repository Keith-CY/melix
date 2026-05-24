# Issue 350 Profile Proof Receipts

## Goal

Add a narrow serving acceleration profile proof and admission receipt surface for
effective config and diagnostics artifacts.

This slice extends the existing issue #351 serving profile contract without
crossing into model download, signature, checksum, extraction, or activation
installation work.

## Scope

- Emit stable machine-readable receipt fields for each requested serving profile.
- Record requested and effective profile identifiers, profile mode, proof matrix
  identity, verification status, admission status, refusal or fallback reason,
  and recovery hint.
- Keep the default `balanced` profile admitted without a proof row.
- Refuse optimized or non-baseline profile admission when a passing proof row is
  missing.
- Preserve the existing acceleration capability receipt and request admission
  boundary.
- Make diagnostics `effective-config.json` snapshots stable for the new receipt
  fields.

## Out Of Scope

- Download worker fallback, retries, signature verification, checksums, archive
  extraction, or activation installation boundaries.
- Implementing a new acceleration kernel or speculative decoding algorithm.
- Claiming performance improvements without benchmark evidence.
- Promoting experimental profiles to release-clear defaults.

## Receipt Contract

The profile receipt is represented as stable string fields that can travel
through model capability metadata, request audit metadata, and diagnostics
effective config snapshots:

| Field | Meaning |
| --- | --- |
| `requested_profile` | Operator-requested serving profile after normalization. |
| `effective_profile` | Profile actually admitted for the request. |
| `profile_mode` | `default`, `optimized`, or `experimental`. |
| `proof_matrix_id` | Repository-owned proof row identifier, or empty when no proof row is required. |
| `verification_status` | `not_required`, `passed`, `missing`, or `failed`. |
| `profile_admission_status` | `admitted`, `refused`, or `experimental_unverified`. |
| `fallback_reason` | Empty on clean admission; typed reason when refused or downgraded. |
| `recovery_hint` | Operator action for the refused or unverified profile. |

`balanced` is the default baseline profile and does not require a proof row. A
profile whose resolved acceleration mode is not `baseline`, or whose metadata
declares `profile_mode=optimized`, requires a passing proof row before request
admission can enable it.

## Implementation Plan

1. Add focused Swift tests for profile receipt admission:
   - `balanced` produces an admitted `not_required` receipt.
   - `throughput` without a proof row is rejected as `experimental_unverified`.
   - `throughput` with a passing proof row is admitted and exposes audit
     metadata.
2. Add a focused request-coordinator test proving an unverified optimized
   profile is refused before worker dispatch.
3. Add a Python diagnostics test that writes `effective-config.json` and asserts
   the profile receipt fields survive stable JSON serialization.
4. Implement the profile receipt helper in the control plane using existing
   profile metadata and acceleration receipt metadata maps.
5. Thread the receipt through request audit metadata and refusal handling.
6. Update the serving diagnostics runbook with the profile proof receipt
   fields and interpretation rules.

## Verification

- Focused Swift red/green tests for model capability receipts and request
  coordinator admission.
- Focused Python red/green diagnostics test.
- `swift test --package-path services/control-plane-swift --filter ModelCatalogTests`
- `swift test --package-path services/control-plane-swift --filter RequestCoordinatorTests`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_serving_diagnostics.py`
- Python changed-scope coverage when feasible.
- `git diff --check`

## Metrics

The changed runtime path adds string receipt construction and metadata merging
before existing request admission. It does not add worker probes, model loading,
download checks, or token-path instrumentation. Success is measured by stable
receipt fields in diagnostics artifacts and deterministic pre-dispatch refusal
for unverified optimized profiles.
