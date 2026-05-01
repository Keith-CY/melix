from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from worker.model_ops.job_registry import ModelOpsJobRegistry


def test_collect_restore_manifest_paths_scans_expected_operations_once(tmp_path: Path) -> None:
    jobs_root = tmp_path / "jobs"
    (jobs_root / "train_lora" / "model-ops-0002").mkdir(parents=True)
    (jobs_root / "train_lora" / "model-ops-abc").mkdir(parents=True)
    (jobs_root / "activate_adapter" / "model-ops-0001" / "one").mkdir(parents=True)
    (jobs_root / "activate_adapter" / "model-ops-0001" / "two").mkdir(parents=True)
    (jobs_root / "remove_derived_model" / "model-ops-0003").mkdir(parents=True)
    (jobs_root / "other" / "ignored").mkdir(parents=True)

    train_manifest = jobs_root / "train_lora" / "model-ops-0002" / "train_lora.adapter.json"
    activate_manifest = (
        jobs_root / "activate_adapter" / "model-ops-0001" / "one" / "manifest.json"
    )
    remove_manifest = jobs_root / "remove_derived_model" / "model-ops-0003" / "remove_derived_model.lifecycle.json"

    train_manifest.write_text(json.dumps({"operation": "train_lora"}), encoding="utf-8")
    activate_manifest.write_text(json.dumps({"operation": "activate_adapter"}), encoding="utf-8")
    remove_manifest.write_text(json.dumps({"operation": "remove_derived_model"}), encoding="utf-8")

    paths = ModelOpsJobRegistry._collect_restore_manifest_paths(jobs_root)

    assert paths["train_lora"] == [train_manifest]
    assert paths["activate_adapter"] == [activate_manifest]
    assert paths["remove_derived_model"] == [remove_manifest]


def test_job_registry_restore_scans_manifest_directories_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    jobs_root = tmp_path / "jobs"
    (jobs_root / "train_lora" / "model-ops-0001").mkdir(parents=True)
    (jobs_root / "activate_adapter" / "model-ops-0002" / "one").mkdir(parents=True)
    (jobs_root / "remove_derived_model" / "model-ops-0003").mkdir(parents=True)

    (jobs_root / "train_lora" / "model-ops-0001" / "train_lora.adapter.json").write_text(
        json.dumps(
            {
                "job_id": "model-ops-0001",
                "operation": "train_lora",
                "source_model": "src-1",
            }
        ),
        encoding="utf-8",
    )
    (jobs_root / "activate_adapter" / "model-ops-0002" / "one" / "manifest.json").write_text(
        json.dumps(
            {
                "job_id": "model-ops-0002",
                "operation": "activate_adapter",
                "source_model": "src-2",
                "derived_model_id": "derived-2",
            }
        ),
        encoding="utf-8",
    )
    (jobs_root / "remove_derived_model" / "model-ops-0003" / "remove_derived_model.lifecycle.json").write_text(
        json.dumps(
            {
                "job_id": "model-ops-0003",
                "operation": "remove_derived_model",
                "source_model": "src-3",
            }
        ),
        encoding="utf-8",
    )

    scan_calls: list[str] = []
    original_scandir = __import__("os").scandir

    def tracked_scandir(path: str | bytes | Path) -> Any:
        scan_calls.append(str(path))
        return original_scandir(path)

    monkeypatch.setattr(__import__("os"), "scandir", tracked_scandir)

    registry = ModelOpsJobRegistry(jobs_root=jobs_root)

    assert set(registry._jobs) == {"model-ops-0003", "model-ops-0002", "model-ops-0001"}
    assert any(str(jobs_root / "train_lora") == call for call in scan_calls)
    assert any(str(jobs_root / "activate_adapter") == call for call in scan_calls)
    assert any(str(jobs_root / "remove_derived_model") == call for call in scan_calls)
    assert len(scan_calls) <= 9


def test_json_safe_reuses_clean_containers_and_copies_only_changed_branch() -> None:
    clean = {"rows": [{"pct": 1.0, "label": "ready"}]}

    assert ModelOpsJobRegistry._json_safe(clean) is clean

    unsafe = {"rows": [{"pct": math.nan, "label": "bad"}], "other": {"pct": 1.0}}
    safe = ModelOpsJobRegistry._json_safe(unsafe)

    assert safe == {"rows": [{"pct": None, "label": "bad"}], "other": {"pct": 1.0}}
    assert safe is not unsafe
    assert safe["rows"] is not unsafe["rows"]
    assert safe["other"] is unsafe["other"]
