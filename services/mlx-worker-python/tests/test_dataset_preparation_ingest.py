from __future__ import annotations

import json
from pathlib import Path
import sys

from worker.productization.dataset_preparation import (
    DatasetIngestRequest,
    prepare_dataset_ingest,
)


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
WORKSPACE_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures/workspace/m-courtyard-smoke.dev.v1/workspace-manifest.json"
)


def test_dataset_ingest_receipt_reports_independent_cleaning_controls(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "raw-inputs"
    output_root = tmp_path / "prepared"
    input_root.mkdir()
    (input_root / "notes.txt").write_text(
        "Contact jane@example.com about Melix.\n",
        encoding="utf-8",
    )
    (input_root / "guide.md").write_text("# Setup\n\n- Run melix\n- Verify output\n", encoding="utf-8")
    (input_root / "worker.py").write_text(
        "def run():\n    return 'token sk-test-secret should be masked'\n",
        encoding="utf-8",
    )
    (input_root / "rows.jsonl").write_text(
        '{"id":"row-1","text":"Alpha structured row"}\n'
        '{"id":"row-2","text":"Alpha structured row"}\n'
        '{"id":"row-3","text":"Alpha structured row."}\n',
        encoding="utf-8",
    )
    (input_root / "array.json").write_text(
        '[{"text":"JSON array row one"},{"text":"JSON array row two"}]\n',
        encoding="utf-8",
    )
    (input_root / "table.csv").write_text(
        "id,text\ncsv-1,CSV structured row\n",
        encoding="utf-8",
    )
    (input_root / "table.tsv").write_text(
        "id\ttext\ntsv-1\tTSV structured row\n",
        encoding="utf-8",
    )
    (input_root / "paper.pdf.txt").write_text(
        "PDF extracted text fixture with phone 415-555-0100.\n",
        encoding="utf-8",
    )
    (input_root / "brief.docx.txt").write_text(
        "DOCX extracted text fixture.\n",
        encoding="utf-8",
    )

    receipt = prepare_dataset_ingest(
        DatasetIngestRequest(
            workspace_project_id="m-courtyard-demo",
            workspace_manifest_path=_write_ready_workspace_manifest(tmp_path),
            input_path=input_root,
            output_dir=output_root,
            dataset_preparation_id="prep-demo",
            pii_mask=True,
            exact_dedup=True,
            fuzzy_dedup=True,
            segmentation=True,
            segmentation_strategy="paragraph",
        )
    )

    assert receipt["schema_version"] == "melix.dataset_ingest_receipt.v1"
    assert receipt["status"] == "ready"
    assert receipt["workspace_project_id"] == "m-courtyard-demo"
    assert receipt["dataset_preparation_id"] == "prep-demo"
    assert receipt["cleaning_controls"] == {
        "pii_mask": {"enabled": True, "policy_id": "melix.pii_mask.local.v1"},
        "exact_dedup": {"enabled": True, "policy_id": "melix.exact_dedup.sha256.v1"},
        "fuzzy_dedup": {"enabled": True, "policy_id": "melix.fuzzy_dedup.tokens.v1"},
    }
    assert receipt["segmentation_policy"] == {
        "enabled": True,
        "strategy": "paragraph",
        "policy_id": "melix.segmentation.paragraph.v1",
    }
    assert {item["source_kind"] for item in receipt["source_inventory"]} == {
        "text",
        "markdown",
        "code",
        "structured_data",
        "pdf",
        "docx",
    }
    assert receipt["quality_control_summary"]["source_file_count"] == 9
    assert receipt["quality_control_summary"]["pii_mask_count"] == 3
    assert receipt["quality_control_summary"]["exact_dedup_count"] == 1
    assert receipt["quality_control_summary"]["fuzzy_dedup_count"] == 1
    assert receipt["metrics"]["source_file_count"] == 9
    assert receipt["metrics"]["source_record_count"] == 12
    assert receipt["metrics"]["segment_count"] >= 5
    assert receipt["metrics"]["pii_mask_count"] == 3
    assert receipt["metrics"]["exact_dedup_count"] == 1
    assert receipt["metrics"]["fuzzy_dedup_count"] == 1
    assert receipt["metrics"]["fuzzy_dedup_ratio"] > 0
    assert receipt["metrics"]["ingest_throughput_bytes_per_second"] > 0
    assert receipt["metrics"]["segmentation_latency_ms"] >= 0
    assert receipt["metrics"]["workspace_preflight_status"] == "ready"

    segments_path = output_root / "segments.jsonl"
    receipt_path = output_root / "dataset-ingest-receipt.json"
    assert receipt["segment_artifacts"] == {
        "segments_path": str(segments_path),
        "receipt_path": str(receipt_path),
    }
    segment_rows = [
        json.loads(line)
        for line in segments_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert all("jane@example.com" not in row["text"] for row in segment_rows)
    assert all("415-555-0100" not in row["text"] for row in segment_rows)
    assert all("sk-test-secret" not in row["text"] for row in segment_rows)
    assert any(row["source_kind"] == "code" and row["metadata"]["language"] == "python" for row in segment_rows)
    assert any(row["text"] == "JSON array row one" for row in segment_rows)
    assert any(row["text"] == "CSV structured row" for row in segment_rows)
    assert any(row["text"] == "TSV structured row" for row in segment_rows)
    assert json.loads(receipt_path.read_text(encoding="utf-8")) == receipt


def test_dataset_ingest_controls_can_be_inspected_independently(tmp_path: Path) -> None:
    input_root = tmp_path / "raw-inputs"
    output_root = tmp_path / "prepared"
    input_root.mkdir()
    (input_root / "notes.txt").write_text(
        "Email jane@example.com.\n\nEmail jane@example.com.\n",
        encoding="utf-8",
    )

    receipt = prepare_dataset_ingest(
        DatasetIngestRequest(
            workspace_project_id="m-courtyard-demo",
            workspace_manifest_path=_write_ready_workspace_manifest(tmp_path),
            input_path=input_root,
            output_dir=output_root,
            dataset_preparation_id="prep-no-cleaning",
            pii_mask=False,
            exact_dedup=False,
            fuzzy_dedup=False,
            segmentation=True,
        )
    )

    assert receipt["cleaning_controls"]["pii_mask"]["enabled"] is False
    assert receipt["cleaning_controls"]["exact_dedup"]["enabled"] is False
    assert receipt["cleaning_controls"]["fuzzy_dedup"]["enabled"] is False
    assert receipt["metrics"]["pii_mask_count"] == 0
    assert receipt["metrics"]["exact_dedup_count"] == 0
    assert receipt["metrics"]["fuzzy_dedup_count"] == 0
    segment_text = (output_root / "segments.jsonl").read_text(encoding="utf-8")
    assert "jane@example.com" in segment_text


def test_dataset_ingest_emits_typed_operator_failures(tmp_path: Path) -> None:
    input_root = tmp_path / "raw-inputs"
    output_root = tmp_path / "prepared"
    input_root.mkdir()
    (input_root / "empty.txt").write_text("", encoding="utf-8")
    (input_root / "archive.bin").write_bytes(b"\x00\x01")

    receipt = prepare_dataset_ingest(
        DatasetIngestRequest(
            workspace_project_id="m-courtyard-demo",
            workspace_manifest_path=_write_ready_workspace_manifest(tmp_path),
            input_path=input_root,
            output_dir=output_root,
            dataset_preparation_id="prep-blocked",
        )
    )

    assert receipt["status"] == "blocked"
    assert {failure["code"] for failure in receipt["operator_failures"]} == {
        "DATASET_INGEST_EMPTY_SOURCE",
        "DATASET_INGEST_UNSUPPORTED_SOURCE",
    }
    assert {failure["id"] for failure in receipt["operator_failures"]} == {
        "dataset-ingest-empty-source-empty-txt",
        "dataset-ingest-unsupported-source-archive-bin",
    }
    assert all(failure["detail"] for failure in receipt["operator_failures"])
    assert all(failure["recovery_hint"] for failure in receipt["operator_failures"])
    assert receipt["metrics"]["source_record_count"] == 0
    assert receipt["metrics"]["segment_count"] == 0


def test_dataset_ingest_blocks_on_workspace_preflight_before_segmenting_sources(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "raw-inputs"
    output_root = tmp_path / "prepared"
    input_root.mkdir()
    (input_root / "notes.txt").write_text("This source should not be segmented.\n", encoding="utf-8")
    manifest_path = _write_ready_workspace_manifest(tmp_path, skip_roots={"jobs"})

    receipt = prepare_dataset_ingest(
        DatasetIngestRequest(
            workspace_project_id="m-courtyard-demo",
            workspace_manifest_path=manifest_path,
            input_path=input_root,
            output_dir=output_root,
            dataset_preparation_id="prep-workspace-blocked",
        )
    )

    assert receipt["status"] == "blocked"
    assert receipt["source_inventory"] == []
    assert receipt["quality_control_summary"]["segment_count"] == 0
    assert receipt["operator_failures"][0]["code"] == "WORKSPACE_ROOT_MISSING"
    assert receipt["operator_failures"][0]["recovery_hint"]
    assert receipt["workspace_preflight_receipt"]["status"] == "blocked"
    assert receipt["workspace_preflight_receipt"]["checks"][0]["code"]
    assert Path(receipt["workspace_preflight_receipt_path"]).is_file()
    assert not (output_root / "segments.jsonl").exists()


def test_dataset_ingest_cli_writes_stable_json_receipt(tmp_path: Path) -> None:
    import dataset_preparation_ingest

    input_root = tmp_path / "raw-inputs"
    output_root = tmp_path / "prepared"
    receipt_path = tmp_path / "reports/dataset-ingest-receipt.json"
    manifest_path = _write_ready_workspace_manifest(tmp_path)
    input_root.mkdir()
    (input_root / "notes.txt").write_text("Email jane@example.com.\n", encoding="utf-8")

    exit_code = dataset_preparation_ingest.main(
        [
            "--workspace-project-id",
            "m-courtyard-demo",
            "--workspace-manifest",
            str(manifest_path),
            "--input",
            str(input_root),
            "--output-dir",
            str(output_root),
            "--dataset-preparation-id",
            "prep-cli",
            "--output",
            str(receipt_path),
            "--pii-mask",
            "true",
            "--exact-dedup",
            "false",
            "--fuzzy-dedup",
            "false",
            "--segmentation",
            "true",
        ]
    )

    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["schema_version"] == "melix.dataset_ingest_receipt.v1"
    assert payload["dataset_preparation_id"] == "prep-cli"
    assert payload["cleaning_controls"]["pii_mask"]["enabled"] is True
    assert payload["cleaning_controls"]["exact_dedup"]["enabled"] is False
    assert payload["metrics"]["pii_mask_count"] == 1


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
