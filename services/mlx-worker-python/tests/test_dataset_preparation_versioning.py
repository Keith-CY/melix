from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from worker.productization.dataset_preparation import (
    DatasetIngestRequest,
    DatasetRetryFailedRequest,
    DatasetVersionRequest,
    _quality_summary,
    _sample_output_length_stats,
    _sample_output_lengths,
    list_dataset_versions,
    prepare_dataset_ingest,
    prepare_dataset_version,
    retry_failed_dataset_version,
)


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
WORKSPACE_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures/workspace/m-courtyard-smoke.dev.v1/workspace-manifest.json"
)


def test_dataset_version_writes_schema_backed_package_and_quality_summary(
    tmp_path: Path,
) -> None:
    ingest_receipt = _prepare_ingest_fixture(tmp_path)
    segment_ids = _segment_ids_from_receipt(ingest_receipt)
    output_root = tmp_path / "datasets"
    manifest_path = Path(str(ingest_receipt["workspace_manifest_path"]))

    version = prepare_dataset_version(
        DatasetVersionRequest(
            workspace_manifest_path=manifest_path,
            ingest_receipt_path=Path(ingest_receipt["segment_artifacts"]["receipt_path"]),
            output_root=output_root,
            dataset_id="support-chat",
            version_id="support-chat-v1",
            created_at="2026-05-24T01:02:03Z",
            mode="chat",
            generator_model="melix.local.dataset-versioner.v1",
            output_kind="training",
            output_format="prompt_completion",
            validation_ratio=0.5,
            fail_segment_ids=(segment_ids[-1],),
        )
    )

    version_dir = output_root / "support-chat" / "versions" / "support-chat-v1"
    assert version["schema_version"] == "melix.dataset_version.v1"
    assert version["status"] == "ready"
    assert version["dataset_id"] == "support-chat"
    assert version["version_id"] == "support-chat-v1"
    assert version["created_at"] == "2026-05-24T01:02:03Z"
    assert version["workspace_project_id"] == "m-courtyard-demo"
    assert version["source_file_count"] == 1
    assert version["source_inventory"][0]["source_uri"] == "notes.txt"
    assert version["source_record_count"] == 1
    assert version["segment_count"] == 3
    assert version["mode"] == "chat"
    assert version["generator_model"] == "melix.local.dataset-versioner.v1"
    assert version["output_kind"] == "training"
    assert version["output_format"] == "prompt_completion"
    assert version["train_count"] == 1
    assert version["validation_count"] == 1
    assert version["failed_count"] == 1
    assert version["failed_segment_ids"] == [segment_ids[-1]]
    assert version["quality_summary_path"] == str(version_dir / "quality-summary.json")
    assert version["package_manifest_path"] == str(version_dir / "manifest.json")
    assert version["samples_path"] == str(version_dir / "samples.jsonl")
    assert version["validation_samples_path"] == str(version_dir / "valid.jsonl")
    assert version["failed_segments_path"] == str(version_dir / "failed-segments.jsonl")
    assert version["metrics"]["generated_sample_count"] == 2
    assert version["metrics"]["failed_sample_count"] == 1

    assert json.loads((version_dir / "dataset-version.json").read_text(encoding="utf-8")) == version
    manifest = json.loads((version_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "melix.training_dataset_package.v1"
    assert manifest["dataset_id"] == "support-chat"
    assert manifest["sample_count"] == 1
    assert manifest["validation_sample_count"] == 1
    assert manifest["quality_summary_path"] == str(version_dir / "quality-summary.json")

    sample_rows = _jsonl_rows(version_dir / "samples.jsonl")
    validation_rows = _jsonl_rows(version_dir / "valid.jsonl")
    failed_rows = _jsonl_rows(version_dir / "failed-segments.jsonl")
    assert len(sample_rows) == 1
    assert len(validation_rows) == 1
    assert failed_rows[0]["segment_id"] == segment_ids[-1]
    assert sample_rows[0]["source_segment_id"] in version["successful_segment_ids"]
    assert validation_rows[0]["source_segment_id"] in version["successful_segment_ids"]

    quality = json.loads((version_dir / "quality-summary.json").read_text(encoding="utf-8"))
    assert quality["schema_version"] == "melix.dataset_quality_summary.v1"
    assert quality["dataset_id"] == "support-chat"
    assert quality["version_id"] == "support-chat-v1"
    assert quality["score"] < 1.0
    assert quality["grade"] == "C"
    assert quality["success_rate"] == 2 / 3
    assert quality["failed_count"] == 1
    assert quality["train_count"] == 1
    assert quality["validation_count"] == 1
    assert quality["pii_mask_count"] == 1
    assert quality["dedup_ratio"] == 0
    assert quality["metrics"]["quality_scoring_latency_ms"] >= 0


def test_dataset_quality_output_lengths_preserve_completion_and_message_semantics() -> None:
    train_rows = [
        {"completion": "abc"},
        {"completion": 12345},
        {"messages": [{"content": "hi"}, {"content": "there"}, {"role": "tool"}, "skip-me"]},
        {"messages": "not-a-list"},
    ]
    validation_rows = [
        {"completion": "done"},
        {"messages": [{"content": "hello"}, {"content": "world"}, {"role": "tool"}, "skip-too"]},
        {"messages": "not-a-list"},
    ]

    assert _sample_output_lengths(train_rows, validation_rows) == [3, 5, 7, 0, 4, 10, 0]
    assert _sample_output_length_stats(train_rows, validation_rows) == (7, 29, 10)
    assert _sample_output_length_stats([], []) == (0, 0, 0)


def test_dataset_quality_summary_reuses_train_validation_counts() -> None:
    class CountingRows(list[dict[str, object]]):
        len_calls = 0

        def __len__(self) -> int:
            self.len_calls += 1
            return super().__len__()

    train_rows = CountingRows([{"completion": "abc"}, {"completion": "def"}])
    validation_rows = CountingRows([{"messages": [{"content": "hello"}]}])

    summary = _quality_summary(
        request=DatasetVersionRequest(
            workspace_manifest_path=Path("workspace-manifest.json"),
            ingest_receipt_path=Path("ingest-receipt.json"),
            output_root=Path("datasets"),
            dataset_id="support-chat",
            version_id="support-chat-v1",
        ),
        ingest_receipt={"quality_control_summary": {"source_record_count": 3}},
        version_id="support-chat-v1",
        train_rows=train_rows,
        validation_rows=validation_rows,
        failed_count=0,
        latency_ms=0.0,
    )

    assert summary["train_count"] == 2
    assert summary["validation_count"] == 1
    assert summary["metrics"]["generated_sample_count"] == 3
    assert train_rows.len_calls == 1
    assert validation_rows.len_calls == 1


def test_dataset_version_rejects_blocked_workspace_preflight_receipt_before_reading_segments(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "raw-inputs"
    output_root = tmp_path / "prepared"
    input_root.mkdir()
    (input_root / "notes.txt").write_text("This source should not be segmented.\n", encoding="utf-8")
    manifest_path = _write_ready_workspace_manifest(tmp_path, skip_roots={"jobs"})
    ingest_receipt = prepare_dataset_ingest(
        DatasetIngestRequest(
            workspace_project_id="m-courtyard-demo",
            workspace_manifest_path=manifest_path,
            input_path=input_root,
            output_dir=output_root,
            dataset_preparation_id="prep-workspace-blocked",
        )
    )

    with pytest.raises(ValueError) as exc:
        prepare_dataset_version(
            DatasetVersionRequest(
                workspace_manifest_path=manifest_path,
                ingest_receipt_path=Path(str(ingest_receipt["segment_artifacts"]["receipt_path"])),
                output_root=tmp_path / "datasets",
                dataset_id="support-chat",
                version_id="support-chat-v1",
            )
        )

    assert str(exc.value).startswith("DATASET_VERSION_SOURCE_RECEIPT_BLOCKED:")
    assert "WORKSPACE_ROOT_MISSING" in str(exc.value)


def test_dataset_version_listing_is_deterministic_and_reports_latency(
    tmp_path: Path,
) -> None:
    ingest_receipt = _prepare_ingest_fixture(tmp_path)
    output_root = tmp_path / "datasets"
    receipt_path = Path(ingest_receipt["segment_artifacts"]["receipt_path"])
    manifest_path = Path(str(ingest_receipt["workspace_manifest_path"]))
    for version_id, created_at in [
        ("support-chat-v2", "2026-05-24T02:00:00Z"),
        ("support-chat-v1", "2026-05-24T01:00:00Z"),
    ]:
        prepare_dataset_version(
            DatasetVersionRequest(
                workspace_manifest_path=manifest_path,
                ingest_receipt_path=receipt_path,
                output_root=output_root,
                dataset_id="support-chat",
                version_id=version_id,
                created_at=created_at,
                mode="chat",
                generator_model="melix.local.dataset-versioner.v1",
                output_kind="training",
                output_format="prompt_completion",
            )
        )

    listing = list_dataset_versions(
        workspace_manifest_path=manifest_path,
        output_root=output_root,
        dataset_id="support-chat",
    )

    assert listing["schema_version"] == "melix.dataset_version_list.v1"
    assert listing["dataset_id"] == "support-chat"
    assert [item["version_id"] for item in listing["versions"]] == [
        "support-chat-v1",
        "support-chat-v2",
    ]
    assert listing["metrics"]["dataset_version_listing_latency_ms"] >= 0
    assert listing["metrics"]["dataset_version_count"] == 2


def test_dataset_version_listing_uses_scandir_without_path_glob(
    monkeypatch,
    tmp_path: Path,
) -> None:
    ingest_receipt = _prepare_ingest_fixture(tmp_path)
    output_root = tmp_path / "datasets"
    receipt_path = Path(ingest_receipt["segment_artifacts"]["receipt_path"])
    prepare_dataset_version(
        DatasetVersionRequest(
            workspace_manifest_path=tmp_path / "workspace-manifest.json",
            ingest_receipt_path=receipt_path,
            output_root=output_root,
            dataset_id="support-chat",
            version_id="support-chat-v1",
            created_at="2026-05-24T01:00:00Z",
            mode="chat",
            generator_model="melix.local.dataset-versioner.v1",
            output_kind="training",
            output_format="prompt_completion",
        )
    )

    def fail_glob(self: Path, pattern: str):  # pragma: no cover - exercised only on regression
        raise AssertionError(f"list_dataset_versions() should not allocate Path.glob({pattern!r})")

    monkeypatch.setattr(Path, "glob", fail_glob)

    def fail_read_json(path: Path):  # pragma: no cover - exercised only on regression
        raise AssertionError(
            f"list_dataset_versions() should read manifest bytes directly without Path.read_bytes({path!s})"
        )

    monkeypatch.setattr("worker.productization.dataset_preparation._read_json", fail_read_json)

    listing = list_dataset_versions(
        workspace_manifest_path=tmp_path / "workspace-manifest.json",
        output_root=output_root,
        dataset_id="support-chat",
    )

    assert [item["version_id"] for item in listing["versions"]] == ["support-chat-v1"]
    assert listing["metrics"]["dataset_version_count"] == 1


def test_dataset_version_listing_handles_missing_versions_root(tmp_path: Path) -> None:
    listing = list_dataset_versions(
        workspace_manifest_path=tmp_path / "workspace-manifest.json",
        output_root=tmp_path / "datasets",
        dataset_id="missing-dataset",
    )

    assert listing["versions"] == []
    assert listing["metrics"]["dataset_version_count"] == 0


def test_failed_only_retry_copies_successful_samples_without_rewriting(
    tmp_path: Path,
) -> None:
    ingest_receipt = _prepare_ingest_fixture(tmp_path)
    segment_ids = _segment_ids_from_receipt(ingest_receipt)
    output_root = tmp_path / "datasets"
    manifest_path = Path(str(ingest_receipt["workspace_manifest_path"]))
    base_version = prepare_dataset_version(
        DatasetVersionRequest(
            workspace_manifest_path=manifest_path,
            ingest_receipt_path=Path(ingest_receipt["segment_artifacts"]["receipt_path"]),
            output_root=output_root,
            dataset_id="support-chat",
            version_id="support-chat-v1",
            created_at="2026-05-24T01:00:00Z",
            mode="chat",
            generator_model="melix.local.dataset-versioner.v1",
            output_kind="training",
            output_format="prompt_completion",
            fail_segment_ids=(segment_ids[-1],),
        )
    )
    base_dir = output_root / "support-chat" / "versions" / "support-chat-v1"
    base_samples = (base_dir / "samples.jsonl").read_text(encoding="utf-8")

    retry = retry_failed_dataset_version(
        DatasetRetryFailedRequest(
            workspace_manifest_path=manifest_path,
            dataset_version_path=base_dir / "dataset-version.json",
            output_root=output_root,
            version_id="support-chat-v2",
            created_at="2026-05-24T02:00:00Z",
            generator_model="melix.local.dataset-versioner.v1",
        )
    )

    retry_dir = output_root / "support-chat" / "versions" / "support-chat-v2"
    retry_receipt = json.loads((retry_dir / "dataset-retry-receipt.json").read_text(encoding="utf-8"))
    retry_samples = (retry_dir / "samples.jsonl").read_text(encoding="utf-8")
    retry_version = json.loads((retry_dir / "dataset-version.json").read_text(encoding="utf-8"))

    assert retry["schema_version"] == "melix.dataset_retry_receipt.v1"
    assert retry == retry_receipt
    assert retry["base_version_id"] == "support-chat-v1"
    assert retry["retry_version_id"] == "support-chat-v2"
    assert retry["input_failed_segment_count"] == 1
    assert retry["retry_success_count"] == 1
    assert retry["retry_failed_count"] == 0
    assert retry["reused_successful_sample_count"] == base_version["train_count"] + base_version["validation_count"]
    assert retry["rewritten_successful_sample_count"] == 0
    assert retry["failed_retry_success_rate"] == 1.0
    assert retry_samples.startswith(base_samples)
    assert retry_version["failed_count"] == 0
    assert retry_version["train_count"] == 3
    assert retry_version["validation_count"] == 0
    assert retry_version["metrics"]["failed_retry_success_rate"] == 1.0


def test_dataset_preparation_version_script_writes_version_retry_and_list_json(
    tmp_path: Path,
) -> None:
    from dataset_preparation_version import main

    ingest_receipt = _prepare_ingest_fixture(tmp_path)
    segment_ids = _segment_ids_from_receipt(ingest_receipt)
    output_root = tmp_path / "datasets"
    manifest_path = Path(str(ingest_receipt["workspace_manifest_path"]))
    version_output = tmp_path / "version-output.json"
    retry_output = tmp_path / "retry-output.json"
    list_output = tmp_path / "list-output.json"

    assert main(
        [
            "version",
            "--workspace-manifest",
            str(manifest_path),
            "--ingest-receipt",
            str(ingest_receipt["segment_artifacts"]["receipt_path"]),
            "--output-root",
            str(output_root),
            "--dataset-id",
            "support-chat",
            "--version-id",
            "support-chat-v1",
            "--created-at",
            "2026-05-24T01:00:00Z",
            "--mode",
            "chat",
            "--generator-model",
            "melix.local.dataset-versioner.v1",
            "--output-kind",
            "training",
            "--output-format",
            "prompt_completion",
            "--fail-segment-id",
            segment_ids[-1],
            "--output",
            str(version_output),
        ]
    ) == 0
    version = json.loads(version_output.read_text(encoding="utf-8"))
    assert version["version_id"] == "support-chat-v1"
    assert version["failed_count"] == 1

    assert main(
        [
            "retry-failed",
            "--workspace-manifest",
            str(manifest_path),
            "--dataset-version",
            str(output_root / "support-chat" / "versions" / "support-chat-v1" / "dataset-version.json"),
            "--output-root",
            str(output_root),
            "--version-id",
            "support-chat-v2",
            "--created-at",
            "2026-05-24T02:00:00Z",
            "--output",
            str(retry_output),
        ]
    ) == 0
    retry = json.loads(retry_output.read_text(encoding="utf-8"))
    assert retry["retry_success_count"] == 1
    assert retry["rewritten_successful_sample_count"] == 0

    assert main(
        [
            "list-versions",
            "--workspace-manifest",
            str(manifest_path),
            "--output-root",
            str(output_root),
            "--dataset-id",
            "support-chat",
            "--output",
            str(list_output),
        ]
    ) == 0
    listing = json.loads(list_output.read_text(encoding="utf-8"))
    assert [item["version_id"] for item in listing["versions"]] == [
        "support-chat-v1",
        "support-chat-v2",
    ]


def _prepare_ingest_fixture(tmp_path: Path) -> dict[str, object]:
    input_root = tmp_path / "raw-inputs"
    output_root = tmp_path / "prepared"
    input_root.mkdir()
    (input_root / "notes.txt").write_text(
        "Alpha support answer for jane@example.com.\n\n"
        "Beta support answer.\n\n"
        "Gamma support answer.\n",
        encoding="utf-8",
    )
    return prepare_dataset_ingest(
        DatasetIngestRequest(
            workspace_project_id="m-courtyard-demo",
            workspace_manifest_path=_write_ready_workspace_manifest(tmp_path),
            input_path=input_root,
            output_dir=output_root,
            dataset_preparation_id="prep-demo",
            segmentation=True,
            segmentation_strategy="paragraph",
        )
    )


def _segment_ids_from_receipt(receipt: dict[str, object]) -> list[str]:
    artifacts = receipt["segment_artifacts"]
    assert isinstance(artifacts, dict)
    segments_path = Path(str(artifacts["segments_path"]))
    return [row["segment_id"] for row in _jsonl_rows(segments_path)]


def _jsonl_rows(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write_ready_workspace_manifest(
    tmp_path: Path,
    *,
    skip_roots: set[str] | None = None,
) -> Path:
    workspace_root = tmp_path / "workspace"
    manifest = json.loads(WORKSPACE_FIXTURE.read_text(encoding="utf-8"))
    workspace_root.mkdir(parents=True, exist_ok=True)
    manifest_path = workspace_root / "workspace-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    skip_roots = skip_roots or set()
    root_paths = {
        root["root_id"]: root["path"]
        for root in manifest["artifact_roots"]
        if root.get("path") and root["root_id"] not in skip_roots
    }
    for root_path in root_paths.values():
        (workspace_root / root_path).mkdir(parents=True, exist_ok=True)
    for artifact in manifest["artifacts"]:
        root_path = root_paths.get(artifact["root_id"])
        if root_path is None:
            continue
        artifact_path = workspace_root / root_path / artifact["relative_path"]
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(artifact["artifact_id"], encoding="utf-8")
    return manifest_path
