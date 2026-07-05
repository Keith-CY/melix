from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from dataset_ingest_limit_contract import exercise_dataset_ingest_limit_contract
import worker.productization.dataset_preparation as dataset_preparation_module
from worker.productization.dataset_preparation import (
    DatasetIngestRequest,
    _SOURCE_KIND_BY_NAME,
    _SOURCE_KIND_NAME_CACHE_MAX,
    _blocked_ingest_receipt,
    _iter_source_file_paths,
    _normalize_line_endings,
    _record,
    _read_source_text,
    _source_kind,
    _source_kind_for_name,
    _workspace_privacy_detection_evidence,
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


def test_dataset_ingest_source_file_paths_use_scandir_without_rglob(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_root = tmp_path / "raw-inputs"
    (input_root / "b").mkdir(parents=True)
    (input_root / "a").mkdir()
    (input_root / "z.txt").write_text("root\n", encoding="utf-8")
    (input_root / "b" / "b.txt").write_text("b\n", encoding="utf-8")
    (input_root / "a" / "a.txt").write_text("a\n", encoding="utf-8")

    def fail_rglob(self: Path, pattern: str):  # pragma: no cover - failure path only
        raise AssertionError(f"_iter_source_file_paths() should not call Path.rglob({pattern!r})")

    monkeypatch.setattr(Path, "rglob", fail_rglob)

    assert [path.relative_to(input_root).as_posix() for path in _iter_source_file_paths(input_root)] == [
        "a/a.txt",
        "b/b.txt",
        "z.txt",
    ]


def test_dataset_preparation_import_does_not_eagerly_load_privacy_patterns() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import worker.productization.dataset_preparation; "
                "print('worker.productization.privacy_policy_receipts' in sys.modules)"
            ),
        ],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert completed.stdout.strip() == "False"


def test_dataset_ingest_unbounded_source_reader_uses_single_binary_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "notes.txt"
    source_path.write_text("hello\nworld\n", encoding="utf-8")

    class CountingBinaryFile:
        read_calls = 0

        def __enter__(self) -> "CountingBinaryFile":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            self.read_calls += 1
            assert size == -1
            return b"hello\nworld\n"

    counting_file = CountingBinaryFile()

    def counted_open(path: Path, mode: str = "r", *args: object, **kwargs: object) -> CountingBinaryFile:
        assert path == source_path
        assert mode == "rb"
        assert args == ()
        assert kwargs == {}
        return counting_file

    monkeypatch.setattr(Path, "open", counted_open)

    assert _read_source_text(source_path) == "hello\nworld\n"
    assert counting_file.read_calls == 1


def test_dataset_ingest_source_kind_uses_single_suffix_fast_path() -> None:
    _SOURCE_KIND_BY_NAME.clear()

    assert _source_kind(Path("paper.pdf.txt")) == "pdf"
    assert _source_kind(Path("paper.PdF.txt")) == "pdf"
    assert _source_kind(Path("paper.PDF.TXT")) == "pdf"
    assert _source_kind(Path("brief.docx.txt")) == "docx"
    assert _source_kind(Path("brief.DOCX.txt")) == "docx"
    assert _source_kind(Path("brief.DOCX.TXT")) == "docx"
    assert _source_kind(Path("Brief.TXT")) == "text"
    assert _source_kind(Path("notes.text")) == "text"
    assert _source_kind(Path("NOTES.TEXT")) == "text"
    assert _source_kind(Path("README.md")) == "markdown"
    assert _source_kind(Path("script.py")) == "code"
    assert _source_kind(Path("records.jsonl")) == "structured_data"
    assert _source_kind(Path("records.json")) == "structured_data"
    assert _source_kind(Path("records.csv")) == "structured_data"
    assert _source_kind(Path("records.tsv")) == "structured_data"
    assert _source_kind(Path("script.PY")) == "code"
    assert _source_kind(Path("records.JSONL")) == "structured_data"
    assert _source_kind(Path("records.JSON")) == "structured_data"
    assert _source_kind(Path("records.CSV")) == "structured_data"
    assert _source_kind(Path("records.TSV")) == "structured_data"
    assert _source_kind(Path("README")) is None
    assert _source_kind(Path("archive.tar.gz")) is None


def test_dataset_ingest_source_kind_name_helper_reuses_cached_basename_classification() -> None:
    _SOURCE_KIND_BY_NAME.clear()

    assert _source_kind_for_name("sample-0001.txt") == "text"
    assert len(_SOURCE_KIND_BY_NAME) == 1
    assert _source_kind_for_name("sample-0001.txt") == "text"

    assert len(_SOURCE_KIND_BY_NAME) == 1


def test_dataset_ingest_source_kind_name_helper_returns_cached_none_without_reclassifying(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _SOURCE_KIND_BY_NAME.clear()
    _SOURCE_KIND_BY_NAME["README"] = None

    def fail_classify(name: str) -> str | None:  # pragma: no cover - failure path only
        raise AssertionError(f"cached source kind should avoid reclassifying {name!r}")

    monkeypatch.setattr(dataset_preparation_module, "_classify_source_kind_name", fail_classify)

    assert _source_kind_for_name("README") is None


def test_dataset_ingest_source_kind_directly_classifies_path_names_without_cache() -> None:
    _SOURCE_KIND_BY_NAME.clear()

    assert _source_kind(Path("source/sample-0001.txt")) == "text"
    assert _source_kind(Path("other/sample-0001.txt")) == "text"

    assert _SOURCE_KIND_BY_NAME == {}


def test_dataset_ingest_source_kind_name_cache_bypasses_insert_at_bound() -> None:
    _SOURCE_KIND_BY_NAME.clear()
    cached_entries = {f"cached-{index}.txt": "text" for index in range(_SOURCE_KIND_NAME_CACHE_MAX)}
    _SOURCE_KIND_BY_NAME.update(cached_entries)

    assert _source_kind_for_name("next.txt") == "text"

    assert _SOURCE_KIND_BY_NAME == cached_entries


def test_dataset_ingest_record_copies_nonempty_metadata_and_fast_paths_empty_metadata() -> None:
    empty_metadata: dict[str, object] = {}
    empty_record = _record(Path("sample.txt"), "text", "hello\r\n", empty_metadata)

    assert empty_record["text"] == "hello\n"
    assert empty_record["metadata"] == {}
    assert empty_record["metadata"] is not empty_metadata

    metadata = {"language": "python"}
    record = _record(Path("script.py"), "code", "print('hello')", metadata)
    metadata["language"] = "swift"

    assert record["metadata"] == {"language": "python"}


def test_dataset_ingest_record_accepts_pre_normalized_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_normalize(text: str) -> str:  # pragma: no cover - failure path only
        raise AssertionError(f"pre-normalized record text should not be normalized again: {text!r}")

    monkeypatch.setattr(dataset_preparation_module, "_normalize_line_endings", fail_normalize)

    record = _record(Path("sample.txt"), "text", "hello\n", {}, normalized=True)

    assert record["text"] == "hello\n"
    assert record["byte_size"] == len(b"hello\n")


def test_dataset_ingest_normalize_line_endings_fast_paths_lf_only_text() -> None:
    text = "hello\nMelix\n"

    assert _normalize_line_endings(text) == text
    assert _normalize_line_endings("hello\r\nMelix\r") == "hello\nMelix\n"


def test_dataset_ingest_source_file_paths_skips_scandir_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_root = tmp_path / "raw-inputs"
    input_root.mkdir()
    child_dir = input_root / "child"
    file_path = input_root / "ok.txt"

    class _ScandirResult:
        def __init__(self, entries: list[object]) -> None:
            self._entries = entries

        def __enter__(self) -> list[object]:
            return self._entries

        def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
            return False

    class _BadEntry:
        path = os.fspath(input_root / "bad.txt")

        def is_dir(self, *, follow_symlinks: bool) -> bool:
            raise OSError("bad entry")

        def is_file(self, *, follow_symlinks: bool) -> bool:
            raise OSError("bad entry")

    class _ChildDirEntry:
        path = os.fspath(child_dir)

        def is_dir(self, *, follow_symlinks: bool) -> bool:
            return True

        def is_file(self, *, follow_symlinks: bool) -> bool:
            return False

    class _FileEntry:
        path = os.fspath(file_path)

        def is_dir(self, *, follow_symlinks: bool) -> bool:
            return False

        def is_file(self, *, follow_symlinks: bool) -> bool:
            return True

    def fake_scandir(path: object) -> _ScandirResult:
        if os.fspath(path) == os.fspath(input_root):
            return _ScandirResult([_BadEntry(), _ChildDirEntry(), _FileEntry()])
        raise OSError("missing child")

    monkeypatch.setattr("worker.productization.dataset_preparation.os.scandir", fake_scandir)

    assert _iter_source_file_paths(input_root) == [file_path]


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
        "   \n"
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
    assert receipt["workspace_preflight_receipt"]["network_fetch_policy"]["surface"] == "workspace_ingest"
    assert receipt["workspace_preflight_receipt"]["network_fetch_policy"]["action"] == "passed"
    assert receipt["workspace_preflight_receipt"]["privacy_audit_counters"][0]["passed_count"] == 1

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
    assert not any(row["text"].isspace() for row in segment_rows)
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


def test_dataset_ingest_privacy_detector_redacts_source_records_before_segments(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "raw-inputs"
    output_root = tmp_path / "prepared"
    input_root.mkdir()
    (input_root / "notes.txt").write_text(
        'Workspace note with OPENAI_API_KEY = "sk-workspace-secret" and HF_ABCDEF123456.\n',
        encoding="utf-8",
    )

    receipt = prepare_dataset_ingest(
        DatasetIngestRequest(
            workspace_project_id="m-courtyard-demo",
            workspace_manifest_path=_write_ready_workspace_manifest(tmp_path),
            input_path=input_root,
            output_dir=output_root,
            dataset_preparation_id="prep-detector-redact",
            pii_mask=False,
            exact_dedup=False,
            fuzzy_dedup=False,
            segmentation=True,
            privacy_detector_mode="redact",
        )
    )

    assert receipt["status"] == "ready"
    assert receipt["privacy_detector_receipts"] == [
        {
            "schema_version": "melix.privacy_detector_receipt.v1",
            "surface": "workspace_ingest",
            "route_scope": "source_import",
            "detector_id": "melix.pattern_detector.v1",
            "policy_id": "melix.default_privacy_policy.v1",
            "policy_mode": "redact",
            "action": "redacted",
            "categories": ["secret"],
            "match_count": 2,
            "redacted_span_count": 2,
            "blocked_reason": "",
            "confidence_source": "deterministic_pattern",
            "raw_sensitive_span_count": 0,
            "raw_text_included": False,
        }
    ]
    assert receipt["privacy_audit_counters"] == [
        {
            "schema_version": "melix.privacy_audit_counter.v1",
            "surface": "workspace_ingest",
            "route_scope": "source_import",
            "blocked_count": 0,
            "redacted_count": 1,
            "passed_count": 0,
            "raw_sensitive_span_count": 0,
        }
    ]
    assert receipt["metrics"]["privacy_detector_match_count"] == 2
    assert receipt["metrics"]["privacy_detector_redacted_span_count"] == 2
    assert receipt["metrics"]["privacy_detector_latency_ms"] >= 0

    segment_text = (output_root / "segments.jsonl").read_text(encoding="utf-8")
    assert "[REDACTED_SECRET]" in segment_text
    payload = json.dumps(receipt, sort_keys=True) + segment_text
    for raw_fragment in ("OPENAI_API_KEY", "sk-workspace-secret", "HF_ABCDEF123456"):
        assert raw_fragment not in payload

    structured_root = tmp_path / "structured-text-guard-inputs"
    structured_output = tmp_path / "prepared-structured-text-guard"
    structured_root.mkdir()
    (structured_root / "rows.jsonl").write_text(
        '{"id":"row-1","text":"safe workspace note"}\n'
        '{"id":"row-2","text":{"secret":"sk-raw-object-secret"}}\n'
        '{"id":"row-3","text":["alice@example.com"]}\n',
        encoding="utf-8",
    )

    structured_receipt = prepare_dataset_ingest(
        DatasetIngestRequest(
            workspace_project_id="m-courtyard-demo",
            workspace_manifest_path=_write_ready_workspace_manifest(tmp_path),
            input_path=structured_root,
            output_dir=structured_output,
            dataset_preparation_id="prep-structured-text-guard",
            privacy_detector_mode="redact",
        )
    )

    assert structured_receipt["status"] == "blocked"
    failures = [
        failure
        for failure in structured_receipt["operator_failures"]
        if failure["code"] == "DATASET_INGEST_UNSUPPORTED_TEXT_VALUE"
    ]
    assert [failure["metadata"]["row_index"] for failure in failures] == [2, 3]
    assert {failure["metadata"]["value_type"] for failure in failures} == {"dict", "list"}
    assert structured_receipt["quality_control_summary"]["source_record_count"] == 1
    assert structured_receipt["quality_control_summary"]["segment_count"] == 1

    structured_payload = json.dumps(structured_receipt, sort_keys=True)
    assert "sk-raw-object-secret" not in structured_payload
    assert "alice@example.com" not in structured_payload
    assert "{'secret'" not in structured_payload
    assert "[\"alice@example.com\"]" not in structured_payload

    json_array_root = tmp_path / "structured-json-array-inputs"
    json_array_output = tmp_path / "prepared-json-array-text-guard"
    json_array_root.mkdir()
    (json_array_root / "array.json").write_text(
        json.dumps(
            [
                {"text": "first string row"},
                {"text": {"secret": "sk-json-array-object-secret"}},
                {"title": "fallback row", "body": "still supported"},
            ]
        ),
        encoding="utf-8",
    )

    json_array_receipt = prepare_dataset_ingest(
        DatasetIngestRequest(
            workspace_project_id="m-courtyard-demo",
            workspace_manifest_path=_write_ready_workspace_manifest(tmp_path),
            input_path=json_array_root,
            output_dir=json_array_output,
            dataset_preparation_id="prep-json-array-text-guard",
        )
    )

    assert json_array_receipt["status"] == "blocked"
    assert json_array_receipt["quality_control_summary"]["source_record_count"] == 2
    assert json_array_receipt["quality_control_summary"]["segment_count"] == 2
    assert any(
        failure["code"] == "DATASET_INGEST_UNSUPPORTED_TEXT_VALUE"
        and failure["metadata"] == {
            "source_uri": "array.json",
            "row_index": 2,
            "value_type": "dict",
        }
        for failure in json_array_receipt["operator_failures"]
    )

    json_array_segments = [
        json.loads(line)
        for line in Path(json_array_receipt["segment_artifacts"]["segments_path"]).read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert [segment["text"] for segment in json_array_segments] == [
        "first string row",
        "body: still supported title: fallback row",
    ]
    assert "sk-json-array-object-secret" not in json.dumps(
        json_array_receipt,
        sort_keys=True,
    )

    csv_root = tmp_path / "structured-csv-inputs"
    csv_output = tmp_path / "prepared-csv-text-guard"
    csv_root.mkdir()
    (csv_root / "rows.csv").write_text(
        "id,text\n"
        "row-1,first csv row\n"
        "row-2\n",
        encoding="utf-8",
    )

    csv_receipt = prepare_dataset_ingest(
        DatasetIngestRequest(
            workspace_project_id="m-courtyard-demo",
            workspace_manifest_path=_write_ready_workspace_manifest(tmp_path),
            input_path=csv_root,
            output_dir=csv_output,
            dataset_preparation_id="prep-csv-text-guard",
        )
    )

    assert csv_receipt["status"] == "blocked"
    assert csv_receipt["quality_control_summary"]["source_record_count"] == 1
    assert csv_receipt["quality_control_summary"]["segment_count"] == 1
    assert any(
        failure["code"] == "DATASET_INGEST_UNSUPPORTED_TEXT_VALUE"
        and failure["metadata"] == {
            "source_uri": "rows.csv",
            "row_index": 2,
            "value_type": "NoneType",
        }
        for failure in csv_receipt["operator_failures"]
    )

    csv_segments = [
        json.loads(line)
        for line in Path(csv_receipt["segment_artifacts"]["segments_path"]).read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert [segment["text"] for segment in csv_segments] == ["first csv row"]


def test_dataset_ingest_privacy_detector_block_mode_stops_before_segments(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "raw-inputs"
    output_root = tmp_path / "prepared"
    input_root.mkdir()
    (input_root / "notes.txt").write_text(
        "Workspace source with HF_TOKEN=sk-secret,with,commas.\n",
        encoding="utf-8",
    )

    receipt = prepare_dataset_ingest(
        DatasetIngestRequest(
            workspace_project_id="m-courtyard-demo",
            workspace_manifest_path=_write_ready_workspace_manifest(tmp_path),
            input_path=input_root,
            output_dir=output_root,
            dataset_preparation_id="prep-detector-block",
            privacy_detector_mode="block",
        )
    )

    assert receipt["status"] == "blocked"
    assert receipt["rejection_reason"] == "privacy_detector_blocked"
    assert receipt["operator_failures"] == [
        {
            "id": "dataset-ingest-privacy-detector-blocked",
            "code": "DATASET_INGEST_PRIVACY_DETECTOR_BLOCKED",
            "path": "",
            "detail": (
                "Workspace privacy detector blocked 1 sensitive pattern match "
                "across categories: secret."
            ),
            "recovery_hint": (
                "Remove secrets from workspace sources or rerun ingest with "
                "privacy detector redact mode."
            ),
            "reason": "privacy_detector_blocked",
            "categories": ["secret"],
            "match_count": 1,
        }
    ]
    assert receipt["privacy_detector_receipts"][0]["action"] == "blocked"
    assert receipt["privacy_detector_receipts"][0]["blocked_reason"] == "pattern_match_blocked"
    assert receipt["privacy_detector_receipts"][0]["match_count"] == 1
    assert receipt["privacy_audit_counters"][0]["blocked_count"] == 1
    assert receipt["source_inventory"]
    assert not (output_root / "segments.jsonl").exists()
    payload = json.dumps(receipt, sort_keys=True)
    for raw_fragment in ("HF_TOKEN", "sk-secret", "with,commas"):
        assert raw_fragment not in payload


def test_dataset_ingest_privacy_detector_off_does_not_enter_detection_helpers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = [{"text": "OPENAI_API_KEY=sk-default-off"}]

    def fail_aggregate(*_args: object, **_kwargs: object) -> object:  # pragma: no cover - failure path only
        raise AssertionError("privacy detector off mode must not aggregate source records")

    def fail_detect(*_args: object, **_kwargs: object) -> object:  # pragma: no cover - failure path only
        raise AssertionError("privacy detector off mode must not scan source records")

    monkeypatch.setattr(dataset_preparation_module, "aggregate_privacy_detection_results", fail_aggregate)
    monkeypatch.setattr(dataset_preparation_module, "detect_privacy_patterns", fail_detect)

    evidence = _workspace_privacy_detection_evidence(
        records,
        DatasetIngestRequest(
            workspace_project_id="m-courtyard-demo",
            workspace_manifest_path=tmp_path / "workspace-manifest.json",
            input_path=tmp_path / "raw-inputs",
            output_dir=tmp_path / "prepared",
            dataset_preparation_id="prep-detector-off",
            privacy_detector_mode="off",
        ),
    )

    assert evidence.records is records
    assert evidence.receipt["policy_mode"] == "off"
    assert evidence.receipt["action"] == "passed"
    assert evidence.receipt["match_count"] == 0
    assert evidence.audit_counter["passed_count"] == 1


def test_dataset_ingest_privacy_detector_treats_none_text_as_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanned_text: list[str] = []
    real_detect = dataset_preparation_module.detect_privacy_patterns

    def capture_detect(value: str, **kwargs: object) -> object:
        scanned_text.append(value)
        return real_detect(value, **kwargs)

    monkeypatch.setattr(dataset_preparation_module, "detect_privacy_patterns", capture_detect)

    evidence = _workspace_privacy_detection_evidence(
        [{"text": None}],
        DatasetIngestRequest(
            workspace_project_id="m-courtyard-demo",
            workspace_manifest_path=tmp_path / "workspace-manifest.json",
            input_path=tmp_path / "raw-inputs",
            output_dir=tmp_path / "prepared",
            dataset_preparation_id="prep-detector-none",
            privacy_detector_mode="redact",
        ),
    )

    assert scanned_text == [""]
    assert evidence.records == [{"text": None}]
    assert evidence.receipt["action"] == "passed"
    assert evidence.receipt["match_count"] == 0


def test_blocked_ingest_receipt_preserves_passed_privacy_fields_when_only_metrics_default(
    tmp_path: Path,
) -> None:
    passed_receipts = [{"policy_mode": "redact", "action": "redacted", "match_count": 2}]
    passed_counters = [{"redacted_count": 1, "passed_count": 0, "blocked_count": 0}]

    receipt = _blocked_ingest_receipt(
        request=DatasetIngestRequest(
            workspace_project_id="m-courtyard-demo",
            workspace_manifest_path=tmp_path / "workspace-manifest.json",
            input_path=tmp_path / "raw-inputs",
            output_dir=tmp_path / "prepared",
            dataset_preparation_id="prep-blocked-default-metrics",
            privacy_detector_mode="redact",
        ),
        segments_path=tmp_path / "prepared" / "segments.jsonl",
        receipt_path=tmp_path / "prepared" / "dataset-ingest-receipt.json",
        workspace_preflight_receipt_path=tmp_path / "prepared" / "workspace-preflight-receipt.json",
        workspace_preflight_receipt={"status": "ready"},
        operator_failures=[],
        elapsed_ms=1.0,
        source_inventory=[],
        source_file_count=0,
        observed_payload_bytes=0,
        upload_cap_bytes=0,
        source_cap_bytes=0,
        rejection_reason="segment_artifact_write_failed",
        partial_artifact_cleanup={"status": "missing"},
        privacy_detector_receipts=passed_receipts,
        privacy_audit_counters=passed_counters,
        privacy_detector_metrics=None,
    )

    assert receipt["privacy_detector_receipts"] == passed_receipts
    assert receipt["privacy_audit_counters"] == passed_counters
    assert receipt["metrics"]["privacy_detector_match_count"] == 0


def test_dataset_ingest_emits_typed_operator_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_root = tmp_path / "raw-inputs"
    output_root = tmp_path / "prepared"
    input_root.mkdir()
    (input_root / "empty.txt").write_text("", encoding="utf-8")
    (input_root / "blank.txt").write_text(" \n\t\n", encoding="utf-8")
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
        "dataset-ingest-empty-source-blank-txt",
        "dataset-ingest-empty-source-empty-txt",
        "dataset-ingest-unsupported-source-archive-bin",
    }
    assert all(failure["detail"] for failure in receipt["operator_failures"])
    assert all(failure["recovery_hint"] for failure in receipt["operator_failures"])
    assert receipt["metrics"]["source_record_count"] == 0
    assert receipt["metrics"]["segment_count"] == 0

    exercise_dataset_ingest_limit_contract(tmp_path / "ingest-limit-contract", monkeypatch)


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
            "--upload-cap-bytes",
            "1024",
            "--source-cap-bytes",
            "512",
        ]
    )

    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["schema_version"] == "melix.dataset_ingest_receipt.v1"
    assert payload["dataset_preparation_id"] == "prep-cli"
    assert payload["upload_cap_bytes"] == 1024
    assert payload["observed_payload_bytes"] > 0
    assert payload["source_cap_bytes"] == 512
    assert payload["partial_artifact_cleanup"]["status"] == "not_needed"
    assert payload["cleaning_controls"]["pii_mask"]["enabled"] is True
    assert payload["cleaning_controls"]["exact_dedup"]["enabled"] is False
    assert payload["metrics"]["pii_mask_count"] == 1
    assert payload["privacy_detector_receipts"][0]["policy_mode"] == "off"


def test_dataset_ingest_cli_accepts_privacy_detector_mode(tmp_path: Path) -> None:
    import dataset_preparation_ingest

    input_root = tmp_path / "raw-inputs"
    output_root = tmp_path / "prepared"
    receipt_path = tmp_path / "reports/dataset-ingest-receipt.json"
    manifest_path = _write_ready_workspace_manifest(tmp_path)
    input_root.mkdir()
    (input_root / "notes.txt").write_text(
        "Secret HF_TOKEN=sk-secret,with,commas.\n",
        encoding="utf-8",
    )

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
            "prep-cli-detector",
            "--output",
            str(receipt_path),
            "--pii-mask",
            "false",
            "--exact-dedup",
            "false",
            "--fuzzy-dedup",
            "false",
            "--segmentation",
            "true",
            "--privacy-detector-mode",
            "redact",
        ]
    )

    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["privacy_detector_receipts"][0]["policy_mode"] == "redact"
    assert payload["privacy_detector_receipts"][0]["action"] == "redacted"
    output_payload = json.dumps(payload, sort_keys=True)
    assert "sk-secret" not in output_payload
    assert "with,commas" not in output_payload


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
