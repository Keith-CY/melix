#!/usr/bin/env python3

from __future__ import annotations

import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time


REPO_ROOT = Path(
    os.environ.get(
        "MELIX_AGENT_CONTROL_PROBE_REPO_ROOT",
        Path(__file__).resolve().parents[1],
    )
).resolve()
FEATURE_AVAILABLE = all(
    path.is_file()
    for path in (
        REPO_ROOT / "services/control-plane-swift/Package.swift",
        REPO_ROOT / "services/computer-use-broker-swift/Package.swift",
        REPO_ROOT / "apps/macos-menubar/Package.swift",
    )
)

COMMANDS = (
    (
        "control_plane",
        (
            "swift",
            "test",
            "--package-path",
            "services/control-plane-swift",
            "--filter",
            (
                "blockedSnapshotFlushFailurePreservesOneTerminalTruth|"
                "agentOperationsReturnsLiveRuntimeReadModel|"
                "agentOperationsReportsEmptyComputerTargetDiscovery|"
                "agentOperationsReportsComputerTargetDiscoveryFailure|"
                "agentOperationsReportsComputerTargetDiscoveryNotRequested|"
                "exactBinding|longRunDeadlineIsCappedPerBrokerRequest|"
                "failClosedInputs|"
                "approvalOperationPresentationMatchesPolicyContext|"
                "approvalScopePresentationDistinguishesPolicyAndCallTargets|"
                "approvalArgumentReviewBoundsAreExplicit|"
                "approvalDeadlineExpiresBeforeDecisionPersistence|"
                "cancellationReachesActiveModelTransport|"
                "cancellationPersistenceFailureDoesNotCacheSuccess"
            ),
        ),
    ),
    (
        "computer_broker",
        (
            "swift",
            "test",
            "--package-path",
            "services/computer-use-broker-swift",
            "--filter",
            (
                "agedAuthorizationOnlyCancelsSessionOverRealUDS|"
                "signedAuthorizationVerifierFailsClosed|"
                "sessionCancellationClosesIdleSession|"
                "sessionCancellationBoundariesAreTyped"
            ),
        ),
    ),
    (
        "desktop",
        (
            "swift",
            "test",
            "--package-path",
            "apps/macos-menubar",
            "--filter",
            (
                "actStartsTypedAgentRunAndNewChatResetsToAsk|"
                "computerTargetDiscoveryPresentationIsTruthful|"
                "agentApprovalPolicyRefreshAndRevokeUsesCAS|"
                "agentOperationsRefreshUsesTypedRuntimeSnapshot|"
                "chatStopRecordsBackendCancellationBeforeLeavingStreamingState"
            ),
        ),
    ),
)


def _run_component(command: tuple[str, ...], timeout_seconds: int) -> float:
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        stdout=sys.stderr,
        stderr=sys.stderr,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    elapsed_ms = (time.perf_counter() - started) * 1_000
    if completed.returncode != 0:
        raise RuntimeError(
            f"Agent control-surface probe failed with {completed.returncode}: "
            f"{' '.join(command)}"
        )
    return elapsed_ms


def measure(sample_count: int, timeout_seconds: int) -> dict[str, float]:
    samples: dict[str, list[float]] = {
        component: [] for component, _ in COMMANDS
    }
    total_samples: list[float] = []
    for _ in range(sample_count):
        total_started = time.perf_counter()
        for component, command in COMMANDS:
            samples[component].append(
                _run_component(command, timeout_seconds)
            )
        total_samples.append((time.perf_counter() - total_started) * 1_000)
    metrics = {
        f"{component}_test_ms_mean": statistics.fmean(values)
        for component, values in samples.items()
    }
    metrics.update(
        {
            "total_test_ms_mean": statistics.fmean(total_samples),
            "component_count": float(len(COMMANDS)),
            "sample_count": float(sample_count),
            "feature_available_count": 1.0,
        }
    )
    return metrics


def main() -> int:
    sample_count = int(
        os.environ.get("MELIX_AGENT_CONTROL_PROBE_SAMPLES", "1")
    )
    timeout_seconds = int(
        os.environ.get("MELIX_AGENT_CONTROL_PROBE_TIMEOUT_SECONDS", "1200")
    )
    if sample_count < 1 or timeout_seconds < 1:
        raise ValueError("probe samples and timeout must be positive")
    if not FEATURE_AVAILABLE:
        print(
            json.dumps(
                {"feature_available_count": 0.0},
                sort_keys=True,
            )
        )
        return 0
    print(
        json.dumps(
            measure(sample_count, timeout_seconds),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
