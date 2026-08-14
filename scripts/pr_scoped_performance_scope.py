#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_JSON_LOADS = json.loads
_CHANGED_FILES_CACHE: dict[str, tuple[int, int, list[object]]] = {}

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from worker.productization.pr_scoped_performance import build_scope_report  # noqa: E402


def load_changed_files(path: str | Path) -> list[object]:
    path_obj = path if type(path) is Path else Path(path)
    cache_key = str(path_obj)
    stat_result = path_obj.stat()
    cached = _CHANGED_FILES_CACHE.get(cache_key)
    if cached is not None:
        cached_mtime_ns, cached_size, cached_files = cached
        if cached_mtime_ns == stat_result.st_mtime_ns and cached_size == stat_result.st_size:
            return cached_files.copy()
    changed_files = _JSON_LOADS(path_obj.read_bytes())
    if not isinstance(changed_files, list):
        raise ValueError("changed files payload must be a JSON list")
    _CHANGED_FILES_CACHE[cache_key] = (
        stat_result.st_mtime_ns,
        stat_result.st_size,
        changed_files.copy(),
    )
    return changed_files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", required=True)
    parser.add_argument("--changed-files-json", required=True)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    changed_files = load_changed_files(args.changed_files_json)
    scope = build_scope_report(registry_path=args.registry, changed_files=[str(path) for path in changed_files])
    rendered = json.dumps(scope, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
