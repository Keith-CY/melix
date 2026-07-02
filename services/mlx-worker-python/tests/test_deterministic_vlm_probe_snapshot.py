from worker.runtime.deterministic_vlm_runtime import VisionProbeSnapshot


def test_vlm_probe_snapshot_reuses_disabled_speculative_probe_receipt() -> None:
    first = VisionProbeSnapshot(0.0, 0, 0, 0.0)
    second = VisionProbeSnapshot(0.0, 0, 0, 0.0)

    assert first.speculative_probe_receipt is second.speculative_probe_receipt
    assert first.speculative_probe_receipt["enabled"] is False
    assert first.speculative_probe_receipt["status"] == "not_requested"
