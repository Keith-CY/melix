from __future__ import annotations

import json
from pathlib import Path
import runpy
import sys
from collections.abc import Callable

import pytest

from worker.productization import export_target_layout as export_target_layout_module
from worker.productization.export_target_layout import (
    EXPORT_RETENTION_REPORT_SCHEMA_VERSION,
    build_export_target_layout,
    build_layout_metrics_report,
    cleanup_export_target,
    materialize_export_target_layout,
    _runtime_log_ttl_expired,
    _target_relative_path,
)
from worker.productization.export_target_manifest import validate_export_target_manifest_file


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import export_target_layout_retention_report

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "fixtures/runtime-export/target-manifests.dev.v1"
)


def test_export_target_layout_groups_by_adapter_snapshot_target_and_source(
    tmp_path: Path,
) -> None:
    manifest_path = FIXTURE_ROOT / "melix_managed/export-target-manifest.json"
    manifest, report = validate_export_target_manifest_file(
        manifest_path,
        return_manifest=True,
    )
    assert report.ok is True

    layout = build_export_target_layout(tmp_path, manifest)

    assert layout.target_type_segment == "melix_managed"
    assert layout.target_root.relative_to(tmp_path).parts[:8] == (
        "exports",
        "adapters",
        "support-chat-adapter-v1",
        "sha256-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "support-chat-export-v1",
        "targets",
        "melix_managed",
        "support-chat-melix-managed",
    )
    assert layout.manifest_path.name == "export-target-manifest.json"
    assert layout.artifacts_dir == layout.target_root / "artifacts"
    assert layout.retention_report_path == layout.target_root / "retention/retention-report.json"


def test_materialize_export_target_layout_writes_reports_and_placeholder_files(
    tmp_path: Path,
) -> None:
    manifest_path = FIXTURE_ROOT / "ollama/export-target-manifest.json"

    report = materialize_export_target_layout(
        manifest_path,
        tmp_path,
        create_placeholder_files=True,
    )

    assert report["ok"] is True
    target_root = tmp_path / str(report["target_root"])
    assert str(report["target_root"]).endswith(
        "targets/ollama/support-chat-ollama"
    )
    assert (target_root / "export-target-manifest.json").is_file()
    assert (target_root / "artifacts/Modelfile").is_file()
    assert (target_root / "artifacts/blobs/sha256-666666").is_file()
    assert (target_root / "logs/ollama-create.log").is_file()
    assert (tmp_path / str(report["export_report_path"])).is_file()
    retention_payload = json.loads((tmp_path / str(report["retention_report_path"])).read_text(encoding="utf-8"))
    assert retention_payload["schema_version"] == EXPORT_RETENTION_REPORT_SCHEMA_VERSION
    assert retention_payload["retained_file_count"] == 4
    assert retention_payload["cleanable_file_count"] == 0
    assert report["retained_byte_size"] == retention_payload["retained_byte_size"]
    assert report["cleanable_byte_size"] == retention_payload["cleanable_byte_size"]
    assert report["retention_decision_count"] == retention_payload["retention_decision_count"]


def test_materialize_export_target_layout_allows_manifest_already_at_layout_path(
    tmp_path: Path,
) -> None:
    manifest_path = FIXTURE_ROOT / "ollama/export-target-manifest.json"
    manifest, validation_report = validate_export_target_manifest_file(
        manifest_path,
        return_manifest=True,
    )
    assert validation_report.ok is True
    layout = build_export_target_layout(tmp_path, manifest)
    layout.manifest_path.parent.mkdir(parents=True)
    layout.manifest_path.write_text(manifest_path.read_text(encoding="utf-8"), encoding="utf-8")

    report = materialize_export_target_layout(
        layout.manifest_path,
        tmp_path,
        create_placeholder_files=False,
    )

    assert report["ok"] is True
    assert Path(report["manifest_path"]) == layout.manifest_path.relative_to(tmp_path)


def test_materialize_export_target_layout_rejects_paths_outside_target_root(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    manifest_path = _write_manifest(
        tmp_path,
        "ollama",
        lambda manifest: _set_nested(
            manifest,
            "generated_files.0.path",
            "artifacts-link/escape.bin",
        ),
    )
    manifest, validation_report = validate_export_target_manifest_file(
        manifest_path,
        return_manifest=True,
    )
    assert validation_report.ok is True
    layout = build_export_target_layout(workspace_root, manifest)
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    layout.target_root.mkdir(parents=True)
    (layout.target_root / "artifacts-link").symlink_to(outside_dir)

    with pytest.raises(ValueError, match="escapes target root"):
        materialize_export_target_layout(
            manifest_path,
            workspace_root,
            create_placeholder_files=True,
        )

    assert not (outside_dir / "escape.bin").exists()


def test_cleanup_dry_run_preserves_required_and_evidence_and_marks_completed_intermediates_cleanable(
    tmp_path: Path,
) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        "melix_managed",
        lambda manifest: _set_nested(
            manifest,
            "verification_status.state",
            "EXPORT_VERIFICATION_STATE_PASSED",
        ),
    )
    materialized = materialize_export_target_layout(
        manifest_path,
        tmp_path / "workspace",
        create_placeholder_files=True,
    )
    target_root = tmp_path / "workspace" / str(materialized["target_root"])
    intermediate_path = target_root / "intermediates/fusion-plan.json"

    report = cleanup_export_target(
        target_root / "export-target-manifest.json",
        tmp_path / "workspace",
        apply_cleanup=False,
    )

    assert report["ok"] is True
    assert report["retained_file_count"] == 3
    assert report["cleanable_file_count"] == 1
    assert report["deleted_file_count"] == 0
    assert report["retained_byte_size"] == 1054720
    assert report["cleanable_byte_size"] == 1024
    assert intermediate_path.exists()
    decisions = {decision["path"]: decision for decision in report["decisions"]}
    assert decisions["export-target-manifest.json"]["decision"] == "retain"
    assert decisions["intermediates/fusion-plan.json"]["decision"] == "cleanable"


def test_cleanup_apply_deletes_only_cleanable_intermediates(
    tmp_path: Path,
) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        "mlx_runtime",
        lambda manifest: _set_nested(
            manifest,
            "verification_status.state",
            "EXPORT_VERIFICATION_STATE_WAIVED",
        ),
    )
    materialized = materialize_export_target_layout(
        manifest_path,
        tmp_path / "workspace",
        create_placeholder_files=True,
    )
    target_root = tmp_path / "workspace" / str(materialized["target_root"])
    required_path = target_root / "artifacts/model.safetensors"
    intermediate_path = target_root / "intermediates/merge.tmp.safetensors"

    report = cleanup_export_target(
        target_root / "export-target-manifest.json",
        tmp_path / "workspace",
        apply_cleanup=True,
    )

    assert report["deleted_file_count"] == 1
    assert report["deleted_byte_size"] == 524288
    assert required_path.exists()
    assert not intermediate_path.exists()
    assert (target_root / "smoke/smoke-receipt.json").is_file()
    assert (target_root / "diagnostics/diagnostics-receipt.json").is_file()
    assert (target_root / "retention/retention-report.json").is_file()
    decisions = {decision["path"]: decision for decision in report["decisions"]}
    assert decisions["artifacts/model.safetensors"]["deleted"] is False
    assert decisions["intermediates/merge.tmp.safetensors"]["deleted"] is True


def test_cleanup_rejects_paths_outside_target_root(
    tmp_path: Path,
) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        "mlx_runtime",
        lambda manifest: _set_nested(
            manifest,
            "verification_status.state",
            "EXPORT_VERIFICATION_STATE_WAIVED",
        ),
    )
    materialized = materialize_export_target_layout(
        manifest_path,
        tmp_path / "workspace",
        create_placeholder_files=True,
    )
    target_root = tmp_path / "workspace" / str(materialized["target_root"])
    target_manifest_path = target_root / "export-target-manifest.json"
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (target_root / "intermediates-link").symlink_to(outside_dir)
    manifest_payload = json.loads(target_manifest_path.read_text(encoding="utf-8"))
    _set_nested(manifest_payload, "intermediate_files.0.path", "intermediates-link/escape.tmp")
    target_manifest_path.write_text(json.dumps(manifest_payload), encoding="utf-8")

    with pytest.raises(ValueError, match="escapes target root"):
        cleanup_export_target(
            target_manifest_path,
            tmp_path / "workspace",
            apply_cleanup=True,
        )

    assert not (outside_dir / "escape.tmp").exists()


def test_cleanup_keeps_intermediates_while_verification_pending(tmp_path: Path) -> None:
    manifest_path = FIXTURE_ROOT / "mlx_runtime/export-target-manifest.json"
    materialized = materialize_export_target_layout(
        manifest_path,
        tmp_path,
        create_placeholder_files=True,
    )
    target_root = tmp_path / str(materialized["target_root"])

    report = cleanup_export_target(
        target_root / "export-target-manifest.json",
        tmp_path,
        apply_cleanup=True,
    )

    assert report["cleanable_file_count"] == 0
    assert report["deleted_file_count"] == 0
    assert (target_root / "intermediates/merge.tmp.safetensors").exists()


def test_runtime_logs_become_cleanable_after_ttl(tmp_path: Path) -> None:
    manifest_path = FIXTURE_ROOT / "ollama/export-target-manifest.json"
    materialized = materialize_export_target_layout(
        manifest_path,
        tmp_path,
        create_placeholder_files=True,
    )
    target_root = tmp_path / str(materialized["target_root"])
    log_path = target_root / "logs/ollama-create.log"
    old_time = 1_700_000_000.0
    log_path.touch()
    import os

    os.utime(log_path, (old_time, old_time))

    report = cleanup_export_target(
        target_root / "export-target-manifest.json",
        tmp_path,
        apply_cleanup=True,
        now=old_time + 604800 + 1,
    )

    assert report["deleted_file_count"] == 1
    assert report["deleted_byte_size"] == 2048
    assert not log_path.exists()
    decisions = {decision["path"]: decision for decision in report["decisions"]}
    assert decisions["logs/ollama-create.log"]["decision"] == "delete_after_ttl"
    assert decisions["logs/ollama-create.log"]["reason"] == "runtime_log_ttl_expired"


def test_runtime_log_ttl_reuses_existing_stat_result(tmp_path: Path) -> None:
    manifest_path = FIXTURE_ROOT / "ollama/export-target-manifest.json"
    manifest, validation_report = validate_export_target_manifest_file(
        manifest_path,
        return_manifest=True,
    )
    assert validation_report.ok is True
    log_path = tmp_path / "ollama-create.log"
    log_path.write_text("log", encoding="utf-8")
    old_time = 1_700_000_000.0
    import os

    os.utime(log_path, (old_time, old_time))
    stat_result = log_path.stat()

    class UnexpectedStatPath:
        def stat(self) -> object:  # pragma: no cover - must not be called
            raise AssertionError("runtime TTL should reuse the caller stat result")

    assert _runtime_log_ttl_expired(
        manifest,
        UnexpectedStatPath(),  # type: ignore[arg-type]
        exists=True,
        now=old_time + 604800 + 1,
        path_stat=stat_result,
    ) is True


def test_runtime_log_ttl_handles_missing_stat_race() -> None:
    manifest_path = FIXTURE_ROOT / "ollama/export-target-manifest.json"
    manifest, validation_report = validate_export_target_manifest_file(
        manifest_path,
        return_manifest=True,
    )
    assert validation_report.ok is True

    class MissingStatPath:
        def stat(self) -> object:
            raise FileNotFoundError

    assert _runtime_log_ttl_expired(
        manifest,
        MissingStatPath(),  # type: ignore[arg-type]
        exists=True,
        now=1_800_000_000.0,
    ) is False


def test_export_target_layout_bounds_path_segments(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        "ollama",
        lambda manifest: _set_nested(
            manifest,
            "adapter_id",
            "adapter-" + "x" * 300,
        ),
    )
    manifest, validation_report = validate_export_target_manifest_file(
        manifest_path,
        return_manifest=True,
    )
    assert validation_report.ok is True

    layout = build_export_target_layout(tmp_path / "workspace", manifest)

    assert max(len(part) for part in layout.target_root.parts) <= 128


def test_export_target_layout_rejects_empty_relative_path(tmp_path: Path) -> None:
    manifest_path = FIXTURE_ROOT / "ollama/export-target-manifest.json"
    manifest, validation_report = validate_export_target_manifest_file(
        manifest_path,
        return_manifest=True,
    )
    assert validation_report.ok is True
    layout = build_export_target_layout(tmp_path, manifest)

    with pytest.raises(ValueError, match="path is empty"):
        _target_relative_path(layout, "")


def test_materialize_placeholder_files_reuses_resolved_target_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = FIXTURE_ROOT / "ollama/export-target-manifest.json"
    manifest, validation_report = validate_export_target_manifest_file(
        manifest_path,
        return_manifest=True,
    )
    assert validation_report.ok is True
    layout = build_export_target_layout(tmp_path, manifest)
    original_target_relative_path = export_target_layout_module._target_relative_path
    resolved_roots: list[Path | None] = []

    def track_resolved_root(
        layout_arg: export_target_layout_module.ExportTargetLayout,
        relative_path: str,
        *,
        resolved_root: Path | None = None,
    ) -> Path:
        resolved_roots.append(resolved_root)
        return original_target_relative_path(  # type: ignore[arg-type]
            layout_arg,
            relative_path,
            resolved_root=resolved_root,
        )

    monkeypatch.setattr(export_target_layout_module, "_target_relative_path", track_resolved_root)

    export_target_layout_module._materialize_placeholder_files(layout, manifest)

    assert resolved_roots
    assert all(resolved_root is not None for resolved_root in resolved_roots)
    assert len({id(resolved_root) for resolved_root in resolved_roots}) == 1


def test_layout_metrics_report_aggregates_target_retention_counts(tmp_path: Path) -> None:
    manifest_paths = sorted(FIXTURE_ROOT.glob("*/export-target-manifest.json"))

    payload = build_layout_metrics_report(
        manifest_paths,
        tmp_path,
        cleanup="dry-run",
        create_placeholder_files=True,
    )

    assert payload["ok"] is True
    assert payload["target_count"] == 4
    assert payload["retention_decision_count"] == 15
    assert payload["retained_byte_size"] == 12141056
    assert payload["cleanable_byte_size"] == 0
    assert payload["deleted_file_count"] == 0
    assert payload["layout_materialization_latency_ms"] >= 0


def test_layout_metrics_report_tracks_report_ok_during_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reports = iter(
        (
            ({"ok": True, "target_root": "one", "retention_report_path": "one.json"}, None),
            ({"ok": False, "errors": ["invalid manifest"]}, None),
        )
    )
    calls = 0

    def fake_materialize(
        manifest_path: Path,
        workspace_root: Path,
        *,
        create_placeholder_files: bool,
        now: float | None,
    ) -> tuple[dict[str, object], dict[str, object] | None]:
        nonlocal calls
        calls += 1
        _ = (manifest_path, workspace_root, create_placeholder_files, now)
        return next(reports)

    monkeypatch.setattr(
        export_target_layout_module,
        "_materialize_export_target_layout_reports",
        fake_materialize,
    )

    payload = build_layout_metrics_report(
        [Path("one.json"), Path("two.json")],
        tmp_path,
        cleanup="dry-run",
    )

    assert calls == 2
    assert payload["target_count"] == 2
    assert payload["ok"] is False
    assert payload["errors"] == ["invalid manifest"]


def test_layout_metrics_report_reuses_materialized_dry_run_retention_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_paths = sorted(FIXTURE_ROOT.glob("*/export-target-manifest.json"))

    def fail_cleanup(*_args: object, **_kwargs: object) -> dict[str, object]:  # pragma: no cover
        raise AssertionError("dry-run metrics should reuse materialized retention reports")

    def fail_read_text(*_args: object, **_kwargs: object) -> str:  # pragma: no cover
        raise AssertionError("dry-run metrics should keep retention reports in memory")

    monkeypatch.setattr(export_target_layout_module, "cleanup_export_target", fail_cleanup)
    monkeypatch.setattr(Path, "read_text", fail_read_text)

    payload = build_layout_metrics_report(
        manifest_paths,
        tmp_path,
        cleanup="dry-run",
        create_placeholder_files=True,
    )

    assert payload["ok"] is True
    assert payload["retention_decision_count"] == 15
    assert payload["retained_byte_size"] == 12141056


def test_export_target_layout_retention_cli_writes_metrics(tmp_path: Path) -> None:
    output_path = tmp_path / "reports/layout-retention.json"

    assert export_target_layout_retention_report.main(["--output", str(output_path)]) == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["schema_version"] == "melix.export_target_layout.metrics.v1"
    assert payload["target_count"] == 4
    assert payload["retention_decision_count"] == 15


def test_export_target_layout_retention_report_default_paths_use_scandir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_glob(self: Path, pattern: str):  # pragma: no cover - regression guard
        raise AssertionError(
            f"_default_manifest_paths() should use os.scandir, not Path.glob({pattern!r})"
        )

    monkeypatch.setattr(Path, "glob", fail_glob)

    assert len(export_target_layout_retention_report._default_manifest_paths()) == 4


def test_export_target_layout_retention_report_default_paths_skip_non_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_root = tmp_path / "targets"
    manifest_dir = target_root / "managed"
    manifest_dir.mkdir(parents=True)
    expected_manifest = manifest_dir / "export-target-manifest.json"
    expected_manifest.write_text("{}", encoding="utf-8")
    (target_root / "not-a-target.txt").write_text("skip", encoding="utf-8")
    monkeypatch.setattr(export_target_layout_retention_report, "DEFAULT_FIXTURE_ROOT", target_root)

    assert export_target_layout_retention_report._default_manifest_paths() == [expected_manifest]


def test_export_target_layout_retention_report_missing_fixture_root_returns_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_root = tmp_path / "missing"
    monkeypatch.setattr(export_target_layout_retention_report, "DEFAULT_FIXTURE_ROOT", missing_root)

    assert export_target_layout_retention_report._default_manifest_paths() == []


def test_runtime_export_layout_retention_probe_env_int_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MELIX_RUNTIME_EXPORT_LAYOUT_PROBE_ITERATIONS", "invalid")
    probe_script = runpy.run_path(str(ROOT / "scripts/runtime_export_layout_retention_probe.py"))

    assert probe_script["_env_int"]("MELIX_RUNTIME_EXPORT_LAYOUT_PROBE_ITERATIONS", 40, 1) == 40


def test_runtime_export_layout_retention_probe_script_emits_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MELIX_RUNTIME_EXPORT_LAYOUT_PROBE_ITERATIONS", "1")
    monkeypatch.setenv("MELIX_RUNTIME_EXPORT_LAYOUT_PROBE_SAMPLES", "1")
    probe_script = runpy.run_path(str(ROOT / "scripts/runtime_export_layout_retention_probe.py"))

    assert probe_script["main"]() == 0

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["target_count"] == 4.0
    assert metrics["retention_decision_count"] == 15.0
    assert metrics["retained_byte_size"] == 12141056.0
    assert metrics["cleanable_byte_size"] == 0.0
    assert metrics["elapsed_ms_mean"] >= 0


def test_runtime_export_layout_retention_probe_manifest_paths_use_scandir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe_script = runpy.run_path(str(ROOT / "scripts/runtime_export_layout_retention_probe.py"))

    def fail_glob(self: Path, pattern: str):  # pragma: no cover - regression guard
        raise AssertionError(
            f"_fixture_manifest_paths() should use os.scandir, not Path.glob({pattern!r})"
        )

    monkeypatch.setattr(Path, "glob", fail_glob)

    assert len(probe_script["_fixture_manifest_paths"]()) == 4


def test_runtime_export_layout_retention_probe_manifest_paths_skip_non_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe_script = runpy.run_path(str(ROOT / "scripts/runtime_export_layout_retention_probe.py"))
    target_root = tmp_path / "targets"
    manifest_dir = target_root / "managed"
    manifest_dir.mkdir(parents=True)
    expected_manifest = manifest_dir / "export-target-manifest.json"
    expected_manifest.write_text("{}", encoding="utf-8")
    (target_root / "not-a-target.txt").write_text("skip", encoding="utf-8")
    monkeypatch.setitem(probe_script["_fixture_manifest_paths"].__globals__, "FIXTURE_ROOT", target_root)

    assert probe_script["_fixture_manifest_paths"]() == [expected_manifest]


def test_runtime_export_layout_retention_probe_manifest_paths_missing_root_returns_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe_script = runpy.run_path(str(ROOT / "scripts/runtime_export_layout_retention_probe.py"))
    missing_root = tmp_path / "missing"
    monkeypatch.setitem(probe_script["_fixture_manifest_paths"].__globals__, "FIXTURE_ROOT", missing_root)

    assert probe_script["_fixture_manifest_paths"]() == []


def _write_manifest(
    tmp_path: Path,
    target: str,
    mutate: Callable[[dict[str, object]], None],
) -> Path:
    manifest = json.loads(
        (FIXTURE_ROOT / target / "export-target-manifest.json").read_text(encoding="utf-8")
    )
    mutate(manifest)
    manifest_path = tmp_path / f"{target}-export-target-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def _set_nested(payload: dict[str, object], field_path: str, value: object) -> None:
    current: object = payload
    parts = field_path.split(".")
    for part in parts[:-1]:
        if isinstance(current, dict):
            current = current[part]
        elif isinstance(current, list):
            current = current[int(part)]
        else:  # pragma: no cover - defensive test helper guard
            raise TypeError(f"cannot descend into {type(current)!r}")
    last = parts[-1]
    if isinstance(current, dict):
        current[last] = value
    elif isinstance(current, list):
        current[int(last)] = value
    else:  # pragma: no cover - defensive test helper guard
        raise TypeError(f"cannot set field on {type(current)!r}")
