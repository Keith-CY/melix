from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
from pathlib import Path


def main() -> None:
    repo_root = Path.cwd()
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(repo_root / "services/mlx-worker-python"))

    from worker.productization.macos_app_bundle import _iter_nested_macho_signing_targets

    target_count = 900
    noise_count = 900
    sample_count = 9
    elapsed_samples: list[float] = []
    discovered_count = 0

    with tempfile.TemporaryDirectory(prefix="melix-macos-signing-targets-probe-") as temp_dir:
        app_path = Path(temp_dir) / "Melix.app"
        macos_dir = app_path / "Contents/MacOS"
        resource_root = app_path / "Contents/Resources"
        macos_dir.mkdir(parents=True)
        resource_root.mkdir(parents=True)

        (macos_dir / "Melix").write_bytes(b"\xfe\xed\xfa\xcflauncher")
        for index in range(target_count - 1):
            helper_dir = resource_root / f"Helper{index:04d}.bundle/Contents/MacOS"
            helper_dir.mkdir(parents=True)
            (helper_dir / f"Helper{index:04d}").write_bytes(b"\xfe\xed\xfa\xcfpayload")
        for index in range(noise_count):
            noise_dir = resource_root / f"Noise{index:04d}.bundle/Contents/Resources"
            noise_dir.mkdir(parents=True)
            (noise_dir / f"plain{index:04d}.txt").write_text("plain\n", encoding="utf-8")

        for _ in range(sample_count):
            started = time.perf_counter()
            targets = _iter_nested_macho_signing_targets(app_path)
            elapsed_samples.append((time.perf_counter() - started) * 1000.0)
            discovered_count = len(targets)

    if discovered_count != target_count:
        raise AssertionError(f"expected {target_count} signing targets, got {discovered_count}")

    print(
        json.dumps(
            {
                "discovered_count": float(discovered_count),
                "elapsed_ms_max": round(max(elapsed_samples), 6),
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "elapsed_ms_min": round(min(elapsed_samples), 6),
                "noise_count": float(noise_count),
                "sample_count": float(sample_count),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
