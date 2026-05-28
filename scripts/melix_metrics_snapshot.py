#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_STALE_AFTER_SECONDS = 30.0
REQUIRED_SOURCES = ("control_plane", "swift_text_worker")
SOURCE_DEFINITIONS = {
    "control_plane": {
        "component": "control_plane",
        "source_kind": "control_plane",
        "env": "MELIX_CONTROL_PLANE_METRICS_PATH",
        "runtime_pattern": "control-plane-metrics*.json",
    },
    "swift_text_worker": {
        "component": "swift_text_worker",
        "source_kind": "worker",
        "env": "MELIX_SWIFT_TEXT_WORKER_METRICS_PATH",
        "runtime_pattern": "swift-text-worker-metrics*.json",
    },
    "python_worker": {
        "component": "python_worker",
        "source_kind": "worker",
        "env": "MELIX_PYTHON_WORKER_METRICS_PATH",
        "runtime_pattern": "python-worker-metrics*.json",
    },
}


@dataclass(frozen=True)
class SourcePath:
    name: str
    path: Path | None
    configured_by: str


def utc_iso_from_unix_seconds(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")


def unix_ms_to_iso(value: int | float | None) -> str | None:
    if value is None:
        return None
    return utc_iso_from_unix_seconds(float(value) / 1000.0)


def normalize_path(value: str | os.PathLike[str] | None) -> Path | None:
    if value is None:
        return None
    text = os.fspath(value).strip()
    if not text:
        return None
    return Path(text).expanduser()


def discover_latest_metrics_path(runtime_dir: Path | None, source_name: str) -> Path | None:
    if runtime_dir is None:
        return None
    pattern = SOURCE_DEFINITIONS[source_name]["runtime_pattern"]
    candidates = [path for path in runtime_dir.expanduser().glob(pattern) if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def resolve_source_paths(
    *,
    control_plane_metrics: Path | None = None,
    swift_text_worker_metrics: Path | None = None,
    python_worker_metrics: Path | None = None,
    runtime_dir: Path | None = None,
    environment: dict[str, str] | None = None,
) -> dict[str, SourcePath]:
    if environment is None:
        environment = dict(os.environ)
    explicit = {
        "control_plane": control_plane_metrics,
        "swift_text_worker": swift_text_worker_metrics,
        "python_worker": python_worker_metrics,
    }
    resolved: dict[str, SourcePath] = {}
    for name, definition in SOURCE_DEFINITIONS.items():
        explicit_path = normalize_path(explicit[name])
        if explicit_path is not None:
            resolved[name] = SourcePath(name=name, path=explicit_path, configured_by="argument")
            continue

        env_path = normalize_path(environment.get(definition["env"]))
        if env_path is not None:
            resolved[name] = SourcePath(name=name, path=env_path, configured_by="environment")
            continue

        runtime_path = discover_latest_metrics_path(runtime_dir, name)
        if runtime_path is not None:
            resolved[name] = SourcePath(name=name, path=runtime_path, configured_by="runtime_dir")
            continue

        resolved[name] = SourcePath(name=name, path=None, configured_by="not_configured")
    return resolved


def load_metrics_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("metrics snapshot must be a JSON object")
    values = payload.get("values")
    if not isinstance(values, dict):
        raise ValueError("metrics snapshot is missing a values object")
    return payload


def _numeric_updated_at(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _freshness_from_payload(
    *,
    payload_updated_at_ms: int | float | None,
    file_modified_at: float | None,
    generated_at_unix_ms: int,
    stale_after_seconds: float,
) -> dict[str, Any]:
    observed_at_unix_ms = payload_updated_at_ms
    observed_source = "payload.updated_at_unix_ms"
    if observed_at_unix_ms is None and file_modified_at is not None:
        observed_at_unix_ms = int(file_modified_at * 1000)
        observed_source = "file.mtime"

    if observed_at_unix_ms is None:
        return {
            "status": "unknown",
            "observed_at_unix_ms": None,
            "observed_at": None,
            "observed_source": "unavailable",
            "age_ms": None,
            "stale_after_seconds": stale_after_seconds,
        }

    age_ms = max(0, generated_at_unix_ms - int(observed_at_unix_ms))
    status = "fresh" if age_ms <= int(stale_after_seconds * 1000) else "stale"
    return {
        "status": status,
        "observed_at_unix_ms": int(observed_at_unix_ms),
        "observed_at": unix_ms_to_iso(observed_at_unix_ms),
        "observed_source": observed_source,
        "age_ms": age_ms,
        "stale_after_seconds": stale_after_seconds,
    }


def _missing_freshness(status: str, stale_after_seconds: float) -> dict[str, Any]:
    return {
        "status": status,
        "observed_at_unix_ms": None,
        "observed_at": None,
        "observed_source": "unavailable",
        "age_ms": None,
        "stale_after_seconds": stale_after_seconds,
    }


def build_source_snapshot(
    source_path: SourcePath,
    *,
    generated_at_unix_ms: int,
    stale_after_seconds: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    definition = SOURCE_DEFINITIONS[source_path.name]
    required = source_path.name in REQUIRED_SOURCES
    source = {
        "component": definition["component"],
        "source_kind": definition["source_kind"],
        "required": required,
        "configured_by": source_path.configured_by,
        "path": str(source_path.path) if source_path.path is not None else None,
        "ok": False,
    }

    if source_path.path is None:
        source["error"] = "metrics source is not configured"
        source["freshness"] = _missing_freshness("not_configured", stale_after_seconds)
        return source, {}

    try:
        stat = source_path.path.stat()
    except OSError as exc:
        source["error"] = f"{type(exc).__name__}: {exc}"
        source["freshness"] = _missing_freshness("missing", stale_after_seconds)
        return source, {}

    try:
        payload = load_metrics_payload(source_path.path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        source["error"] = f"{type(exc).__name__}: {exc}"
        source["freshness"] = _freshness_from_payload(
            payload_updated_at_ms=None,
            file_modified_at=stat.st_mtime,
            generated_at_unix_ms=generated_at_unix_ms,
            stale_after_seconds=stale_after_seconds,
        )
        return source, {}

    values = payload["values"]
    updated_at_unix_ms = _numeric_updated_at(payload.get("updated_at_unix_ms"))
    source.update({
        "ok": True,
        "metric_count": len(values),
        "updated_at_unix_ms": int(updated_at_unix_ms) if updated_at_unix_ms is not None else None,
        "freshness": _freshness_from_payload(
            payload_updated_at_ms=updated_at_unix_ms,
            file_modified_at=stat.st_mtime,
            generated_at_unix_ms=generated_at_unix_ms,
            stale_after_seconds=stale_after_seconds,
        ),
    })
    return source, dict(values)


def build_snapshot(
    *,
    source_paths: dict[str, SourcePath],
    generated_at_unix_ms: int | None = None,
    stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
) -> dict[str, Any]:
    if generated_at_unix_ms is None:
        generated_at_unix_ms = int(time.time() * 1000)
    sources: dict[str, dict[str, Any]] = {}
    source_values: dict[str, dict[str, Any]] = {}
    values: dict[str, Any] = {}
    updated_at_values: list[int] = []
    missing_required_sources: list[str] = []
    errors: list[str] = []

    for name in SOURCE_DEFINITIONS:
        source, metrics = build_source_snapshot(
            source_paths[name],
            generated_at_unix_ms=generated_at_unix_ms,
            stale_after_seconds=stale_after_seconds,
        )
        sources[name] = source
        source_values[name] = metrics
        if source["ok"] is True:
            values.update(metrics)
            updated_at_unix_ms = source.get("updated_at_unix_ms")
            if isinstance(updated_at_unix_ms, int):
                updated_at_values.append(updated_at_unix_ms)
        elif source.get("required") is True:
            missing_required_sources.append(name)
            errors.append(f"{name}: {source.get('error', 'unknown')}")

    ok = not missing_required_sources
    primary_path = next(
        (source["path"] for source in sources.values() if source.get("path")),
        None,
    )
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": unix_ms_to_iso(generated_at_unix_ms),
        "generated_at_unix_ms": generated_at_unix_ms,
        "ok": ok,
        "path": primary_path,
        "updated_at_unix_ms": max(updated_at_values) if updated_at_values else None,
        "missing_required_sources": missing_required_sources,
        "sources": sources,
        "source_values": source_values,
        "values": values,
    }
    if errors:
        snapshot["error"] = "; ".join(errors)
    return snapshot


def build_snapshot_from_paths(
    *,
    control_plane_metrics: Path | None = None,
    swift_text_worker_metrics: Path | None = None,
    python_worker_metrics: Path | None = None,
    runtime_dir: Path | None = None,
    environment: dict[str, str] | None = None,
    generated_at_unix_ms: int | None = None,
    stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
) -> dict[str, Any]:
    source_paths = resolve_source_paths(
        control_plane_metrics=control_plane_metrics,
        swift_text_worker_metrics=swift_text_worker_metrics,
        python_worker_metrics=python_worker_metrics,
        runtime_dir=runtime_dir,
        environment=environment,
    )
    return build_snapshot(
        source_paths=source_paths,
        generated_at_unix_ms=generated_at_unix_ms,
        stale_after_seconds=stale_after_seconds,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Emit a benchmark-consumable Melix metrics snapshot as JSON.",
    )
    parser.add_argument("--control-plane-metrics", type=Path, default=None)
    parser.add_argument("--swift-text-worker-metrics", type=Path, default=None)
    parser.add_argument("--python-worker-metrics", type=Path, default=None)
    parser.add_argument(
        "--runtime-dir",
        type=Path,
        default=normalize_path(os.environ.get("MELIX_RUNTIME_DIR")),
        help="Melix runtime directory used to discover the newest metrics exports.",
    )
    parser.add_argument(
        "--stale-after-seconds",
        type=float,
        default=DEFAULT_STALE_AFTER_SECONDS,
        help="Freshness threshold recorded for each source.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when required metrics sources are missing or invalid.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    snapshot = build_snapshot_from_paths(
        control_plane_metrics=args.control_plane_metrics,
        swift_text_worker_metrics=args.swift_text_worker_metrics,
        python_worker_metrics=args.python_worker_metrics,
        runtime_dir=args.runtime_dir,
        stale_after_seconds=args.stale_after_seconds,
    )
    sys.stdout.write(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    if args.strict and snapshot.get("ok") is not True:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
