from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "melix_metrics_snapshot.py"
MODULE_SPEC = importlib.util.spec_from_file_location("melix_metrics_snapshot", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
snapshot_cli = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = snapshot_cli
MODULE_SPEC.loader.exec_module(snapshot_cli)


def write_metrics(path: Path, *, updated_at_unix_ms: int, values: dict[str, float]) -> None:
    path.write_text(
        json.dumps({
            "updated_at_unix_ms": updated_at_unix_ms,
            "values": values,
        }),
        encoding="utf-8",
    )


def test_build_snapshot_exports_sources_values_and_freshness(tmp_path: Path) -> None:
    control_plane_path = tmp_path / "control-plane-metrics.json"
    swift_worker_path = tmp_path / "swift-text-worker-metrics.json"
    python_worker_path = tmp_path / "python-worker-metrics.json"
    write_metrics(
        control_plane_path,
        updated_at_unix_ms=1_000,
        values={
            "control_plane.text_first_load_ms": 8547.46,
            "http.ttfd_ms": 3447.17,
        },
    )
    write_metrics(
        swift_worker_path,
        updated_at_unix_ms=2_000,
        values={
            "swift_text.prefill_ms": 3706,
            "swift_text.decode_tokens_per_second": 2,
        },
    )
    write_metrics(
        python_worker_path,
        updated_at_unix_ms=1_500,
        values={"python_worker.bootstrap_ms": 25},
    )

    snapshot = snapshot_cli.build_snapshot_from_paths(
        control_plane_metrics=control_plane_path,
        swift_text_worker_metrics=swift_worker_path,
        python_worker_metrics=python_worker_path,
        generated_at_unix_ms=2_500,
        stale_after_seconds=10,
    )

    assert snapshot["ok"] is True
    assert snapshot["path"] == str(control_plane_path)
    assert snapshot["updated_at_unix_ms"] == 2_000
    assert snapshot["missing_required_sources"] == []
    assert snapshot["values"]["control_plane.text_first_load_ms"] == 8547.46
    assert snapshot["values"]["swift_text.prefill_ms"] == 3706
    assert snapshot["source_values"]["control_plane"] == {
        "control_plane.text_first_load_ms": 8547.46,
        "http.ttfd_ms": 3447.17,
    }
    control_source = snapshot["sources"]["control_plane"]
    assert control_source["component"] == "control_plane"
    assert control_source["source_kind"] == "control_plane"
    assert control_source["required"] is True
    assert control_source["configured_by"] == "argument"
    assert control_source["freshness"] == {
        "status": "fresh",
        "observed_at_unix_ms": 1_000,
        "observed_at": "1970-01-01T00:00:01Z",
        "observed_source": "payload.updated_at_unix_ms",
        "age_ms": 1_500,
        "stale_after_seconds": 10,
    }
    python_source = snapshot["sources"]["python_worker"]
    assert python_source["required"] is False
    assert python_source["source_kind"] == "worker"


def test_runtime_dir_discovers_latest_metrics_files(tmp_path: Path) -> None:
    older = tmp_path / "control-plane-metrics-old.json"
    newer = tmp_path / "control-plane-metrics-new.json"
    swift_worker_path = tmp_path / "swift-text-worker-metrics.json"
    write_metrics(older, updated_at_unix_ms=1_000, values={"old": 1})
    write_metrics(newer, updated_at_unix_ms=2_000, values={"new": 2})
    write_metrics(swift_worker_path, updated_at_unix_ms=3_000, values={"swift_text.prefill_ms": 3})
    os.utime(older, (1, 1))
    os.utime(newer, (2, 2))

    resolved = snapshot_cli.resolve_source_paths(
        runtime_dir=tmp_path,
        environment={},
    )
    snapshot = snapshot_cli.build_snapshot(
        source_paths=resolved,
        generated_at_unix_ms=3_100,
    )

    assert resolved["control_plane"].path == newer
    assert resolved["control_plane"].configured_by == "runtime_dir"
    assert snapshot["ok"] is True
    assert snapshot["values"]["new"] == 2


def test_runtime_pattern_matcher_preserves_source_patterns_without_fnmatch(
    monkeypatch,
) -> None:
    def fail_fnmatch(name: str, pattern: str) -> bool:
        raise AssertionError(  # pragma: no cover - failure-only guard.
            f"unexpected fallback for {name!r} {pattern!r}"
        )

    monkeypatch.setattr(snapshot_cli.fnmatch, "fnmatchcase", fail_fnmatch)

    assert snapshot_cli._matches_runtime_pattern(
        "control-plane-metrics-latest.json",
        "control-plane-metrics*.json",
    )
    assert snapshot_cli._matches_runtime_pattern(
        "control-plane-metrics.json",
        "control-plane-metrics.json",
    )
    assert snapshot_cli._matches_runtime_pattern(
        "control-plane-metrics-2026-latest.json",
        "control-plane*latest.json",
    )
    assert not snapshot_cli._matches_runtime_pattern(
        "control-plane-metrics-latest.tmp",
        "control-plane-metrics*.json",
    )
    assert not snapshot_cli._matches_runtime_pattern(
        "old-control-plane-metrics-latest.json",
        "control-plane-metrics*.json",
    )

    monkeypatch.setattr(snapshot_cli.fnmatch, "fnmatchcase", lambda name, pattern: True)
    assert snapshot_cli._matches_runtime_pattern("control-plane.json", "control*plane*.json")


def test_runtime_dir_discovery_uses_single_scandir_without_path_glob(
    tmp_path: Path,
    monkeypatch,
) -> None:
    older = tmp_path / "control-plane-metrics-old.json"
    newer = tmp_path / "control-plane-metrics-new.json"
    ignored = tmp_path / "swift-text-worker-metrics.json"
    write_metrics(older, updated_at_unix_ms=1_000, values={"old": 1})
    write_metrics(newer, updated_at_unix_ms=2_000, values={"new": 2})
    write_metrics(ignored, updated_at_unix_ms=3_000, values={"ignored": 3})
    os.utime(older, (1, 1))
    os.utime(newer, (2, 2))

    def fail_glob(self: Path, pattern: str):
        raise AssertionError(
            f"discover_latest_metrics_path() should not allocate Path.glob({pattern!r}) results"
        )

    original_scandir = snapshot_cli.os.scandir
    scanned_paths: list[str] = []

    def counting_scandir(path: str):
        scanned_paths.append(path)
        return original_scandir(path)

    def fail_runtime_matcher(name: str, pattern: str) -> bool:
        raise AssertionError(  # pragma: no cover - failure-only guard.
            f"single-wildcard discovery should precompute pattern bounds for {name!r} {pattern!r}"
        )

    monkeypatch.setattr(snapshot_cli.Path, "glob", fail_glob)
    monkeypatch.setattr(snapshot_cli.os, "scandir", counting_scandir)
    monkeypatch.setattr(snapshot_cli, "_matches_runtime_pattern", fail_runtime_matcher)

    latest = snapshot_cli.discover_latest_metrics_path(tmp_path, "control_plane")

    assert latest == newer
    assert scanned_paths == [str(tmp_path)]


def test_runtime_dir_discovery_materializes_only_final_latest_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    for index in range(25):
        candidate = tmp_path / f"control-plane-metrics-{index:04d}.json"
        write_metrics(candidate, updated_at_unix_ms=index, values={"value": index})
        os.utime(candidate, (index, index))
    expected = tmp_path / "control-plane-metrics-latest.json"
    write_metrics(expected, updated_at_unix_ms=100, values={"value": 100})
    os.utime(expected, (100, 100))

    original_path = snapshot_cli.Path
    path_constructor_args: list[tuple[object, ...]] = []

    class CountingPath:
        def __new__(cls, *args: object, **kwargs: object):
            path_constructor_args.append(args)
            return original_path(*args, **kwargs)

    monkeypatch.setattr(snapshot_cli, "Path", CountingPath)

    latest = snapshot_cli.discover_latest_metrics_path(tmp_path, "control_plane")

    assert latest == expected
    assert path_constructor_args == [(str(expected),)]


def test_runtime_dir_discovery_preserves_exact_and_multi_wildcard_patterns(
    tmp_path: Path,
    monkeypatch,
) -> None:
    exact_match = tmp_path / "exact-metrics.json"
    exact_noise = tmp_path / "exact-metrics-old.json"
    multi_match = tmp_path / "multi-metrics-new-latest.json"
    multi_noise = tmp_path / "multi-metrics-old.tmp"
    write_metrics(exact_match, updated_at_unix_ms=1_000, values={"exact": 1})
    write_metrics(exact_noise, updated_at_unix_ms=2_000, values={"noise": 2})
    write_metrics(multi_match, updated_at_unix_ms=3_000, values={"multi": 3})
    write_metrics(multi_noise, updated_at_unix_ms=4_000, values={"noise": 4})
    os.utime(exact_match, (1, 1))
    os.utime(multi_match, (2, 2))

    monkeypatch.setitem(
        snapshot_cli.SOURCE_DEFINITIONS,
        "exact_probe",
        {"runtime_pattern": "exact-metrics.json"},
    )
    monkeypatch.setitem(
        snapshot_cli.SOURCE_DEFINITIONS,
        "multi_probe",
        {"runtime_pattern": "multi*latest*.json"},
    )

    assert snapshot_cli.discover_latest_metrics_path(tmp_path, "exact_probe") == exact_match
    assert snapshot_cli.discover_latest_metrics_path(tmp_path, "multi_probe") == multi_match


def test_env_and_not_configured_sources_are_resolved(tmp_path: Path) -> None:
    control_plane_path = tmp_path / "env-control-plane-metrics.json"
    write_metrics(
        control_plane_path,
        updated_at_unix_ms=1_000,
        values={"control_plane.text_first_load_ms": 1},
    )

    assert snapshot_cli.normalize_path(None) is None
    assert snapshot_cli.normalize_path("   ") is None
    assert snapshot_cli.discover_latest_metrics_path(None, "control_plane") is None
    assert snapshot_cli.discover_latest_metrics_path(tmp_path / "missing", "control_plane") is None
    assert snapshot_cli.unix_ms_to_iso(None) is None

    resolved = snapshot_cli.resolve_source_paths(
        environment={"MELIX_CONTROL_PLANE_METRICS_PATH": str(control_plane_path)},
    )

    assert resolved["control_plane"].path == control_plane_path
    assert resolved["control_plane"].configured_by == "environment"
    assert resolved["swift_text_worker"].path is None
    assert resolved["swift_text_worker"].configured_by == "not_configured"


def test_invalid_payload_uses_file_mtime_freshness(tmp_path: Path) -> None:
    invalid_path = tmp_path / "control-plane-metrics.json"
    invalid_path.write_text("not-json", encoding="utf-8")
    os.utime(invalid_path, (1, 1))

    resolved = {
        "control_plane": snapshot_cli.SourcePath(
            name="control_plane",
            path=invalid_path,
            configured_by="argument",
        ),
        "swift_text_worker": snapshot_cli.SourcePath(
            name="swift_text_worker",
            path=None,
            configured_by="not_configured",
        ),
        "python_worker": snapshot_cli.SourcePath(
            name="python_worker",
            path=None,
            configured_by="not_configured",
        ),
    }
    snapshot = snapshot_cli.build_snapshot(
        source_paths=resolved,
        generated_at_unix_ms=2_500,
        stale_after_seconds=1,
    )

    source = snapshot["sources"]["control_plane"]
    assert source["ok"] is False
    assert "JSONDecodeError" in source["error"]
    assert source["freshness"]["status"] == "stale"
    assert source["freshness"]["observed_source"] == "file.mtime"
    assert source["freshness"]["observed_at_unix_ms"] == 1_000


def test_payload_validation_rejects_bad_shapes_and_non_numeric_updates(tmp_path: Path) -> None:
    non_object = tmp_path / "non-object.json"
    non_object.write_text("[]", encoding="utf-8")
    missing_values = tmp_path / "missing-values.json"
    missing_values.write_text("{}", encoding="utf-8")
    bool_update = tmp_path / "bool-update.json"
    bool_update.write_text(
        json.dumps({
            "updated_at_unix_ms": True,
            "values": {"swift_text.prefill_ms": 1},
        }),
        encoding="utf-8",
    )

    for path, message in (
        (non_object, "metrics snapshot must be a JSON object"),
        (missing_values, "metrics snapshot is missing a values object"),
    ):
        try:
            snapshot_cli.load_metrics_payload(path)
        except ValueError as exc:
            assert str(exc) == message
        else:
            raise AssertionError(f"expected ValueError for {path}")

    resolved = {
        "control_plane": snapshot_cli.SourcePath(
            name="control_plane",
            path=None,
            configured_by="not_configured",
        ),
        "swift_text_worker": snapshot_cli.SourcePath(
            name="swift_text_worker",
            path=bool_update,
            configured_by="argument",
        ),
        "python_worker": snapshot_cli.SourcePath(
            name="python_worker",
            path=None,
            configured_by="not_configured",
        ),
    }
    snapshot = snapshot_cli.build_snapshot(source_paths=resolved, generated_at_unix_ms=2_000)
    assert snapshot["sources"]["swift_text_worker"]["ok"] is True
    assert snapshot["sources"]["swift_text_worker"]["updated_at_unix_ms"] is None
    assert snapshot["sources"]["swift_text_worker"]["freshness"]["observed_source"] == "file.mtime"


def test_missing_required_source_is_machine_readable(tmp_path: Path) -> None:
    control_plane_path = tmp_path / "control-plane-metrics.json"
    missing_swift_path = tmp_path / "swift-text-worker-metrics.json"
    write_metrics(
        control_plane_path,
        updated_at_unix_ms=1_000,
        values={"control_plane.text_first_load_ms": 1},
    )

    snapshot = snapshot_cli.build_snapshot_from_paths(
        control_plane_metrics=control_plane_path,
        swift_text_worker_metrics=missing_swift_path,
        generated_at_unix_ms=2_000,
    )

    assert snapshot["ok"] is False
    assert snapshot["missing_required_sources"] == ["swift_text_worker"]
    assert snapshot["sources"]["control_plane"]["ok"] is True
    missing_source = snapshot["sources"]["swift_text_worker"]
    assert missing_source["ok"] is False
    assert missing_source["path"] == str(missing_swift_path)
    assert missing_source["freshness"]["status"] == "missing"
    assert "swift_text_worker" in snapshot["error"]


def test_cli_emits_json_and_strict_mode_fails_on_missing_source(
    tmp_path: Path,
    capsys,
) -> None:
    control_plane_path = tmp_path / "control-plane-metrics.json"
    write_metrics(
        control_plane_path,
        updated_at_unix_ms=1_000,
        values={"control_plane.text_first_load_ms": 1},
    )

    default_exit = snapshot_cli.main([
        "--control-plane-metrics",
        str(control_plane_path),
        "--swift-text-worker-metrics",
        str(tmp_path / "missing-swift-text-worker-metrics.json"),
    ])
    default_payload = json.loads(capsys.readouterr().out)
    assert default_exit == 0
    assert default_payload["ok"] is False
    assert default_payload["missing_required_sources"] == ["swift_text_worker"]

    strict_exit = snapshot_cli.main([
        "--control-plane-metrics",
        str(control_plane_path),
        "--swift-text-worker-metrics",
        str(tmp_path / "missing-swift-text-worker-metrics.json"),
        "--strict",
    ])
    strict_payload = json.loads(capsys.readouterr().out)
    assert strict_exit == 1
    assert strict_payload["ok"] is False
