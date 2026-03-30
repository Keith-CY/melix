from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "python_changed_line_coverage.py"
MODULE_SPEC = importlib.util.spec_from_file_location("python_changed_line_coverage", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
python_changed_line_coverage = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(python_changed_line_coverage)


def test_parse_args_accepts_required_inputs(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "python_changed_line_coverage.py",
            "--coverage-json",
            "/tmp/coverage.json",
            "services/foo.py",
        ],
    )

    args = python_changed_line_coverage.parse_args()

    assert args.coverage_json == "/tmp/coverage.json"
    assert args.diff_from == "HEAD"
    assert args.files == ["services/foo.py"]


def test_run_and_repo_root_delegate_to_subprocess(monkeypatch) -> None:
    observed: list[tuple[list[str], Path | None]] = []

    def fake_check_output(command: list[str], cwd: Path | None = None, text: bool = True) -> str:
        observed.append((command, cwd))
        return "/tmp/repo\n"

    monkeypatch.setattr(python_changed_line_coverage.subprocess, "check_output", fake_check_output)

    assert python_changed_line_coverage.run(["git", "rev-parse"]) == "/tmp/repo\n"
    assert python_changed_line_coverage.repo_root() == Path("/tmp/repo")
    assert observed == [
        (["git", "rev-parse"], None),
        (["git", "rev-parse", "--show-toplevel"], None),
    ]


def test_normalize_file_handles_relative_and_absolute_paths(tmp_path: Path) -> None:
    relative = python_changed_line_coverage.normalize_file(tmp_path, "services/foo.py")
    absolute = python_changed_line_coverage.normalize_file(tmp_path, str(tmp_path / "services/bar.py"))

    assert relative == (tmp_path / "services/foo.py").resolve()
    assert absolute == (tmp_path / "services/bar.py").resolve()


def test_changed_lines_collects_added_hunks(monkeypatch, tmp_path: Path) -> None:
    source_file = (tmp_path / "services/foo.py").resolve()
    diff_text = "\n".join(
        [
            "diff --git a/services/foo.py b/services/foo.py",
            "--- a/services/foo.py",
            "+++ b/services/foo.py",
            "@@ -0,0 +3,2 @@",
            "+first",
            "+second",
            "@@ -10 +12 @@",
            "+third",
        ]
    )

    monkeypatch.setattr(python_changed_line_coverage, "run", lambda command, cwd=None: diff_text)

    changed = python_changed_line_coverage.changed_lines(tmp_path, "HEAD", [source_file])

    assert changed == {source_file: {3, 4, 12}}


def test_load_coverage_normalizes_relative_paths(tmp_path: Path) -> None:
    coverage_json = tmp_path / "coverage.json"
    coverage_json.write_text(
        json.dumps(
            {
                "files": {
                    "services/foo.py": {
                        "executed_lines": [3, 4],
                        "missing_lines": [12],
                    }
                }
            }
        )
    )

    loaded = python_changed_line_coverage.load_coverage(tmp_path, coverage_json)

    assert loaded == {
        (tmp_path / "services/foo.py").resolve(): ({3, 4}, {12}),
    }


def test_main_reports_changed_line_coverage(monkeypatch, tmp_path: Path, capsys) -> None:
    source_file = (tmp_path / "services/foo.py").resolve()
    coverage_json = tmp_path / "coverage.json"
    coverage_json.write_text("{}")

    monkeypatch.setattr(
        python_changed_line_coverage,
        "parse_args",
        lambda: argparse.Namespace(
            coverage_json=str(coverage_json),
            diff_from="HEAD",
            files=[str(source_file)],
        ),
    )
    monkeypatch.setattr(python_changed_line_coverage, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        python_changed_line_coverage,
        "changed_lines",
        lambda root, diff_from, files: {source_file: {3, 4, 12, 13}},
    )
    monkeypatch.setattr(
        python_changed_line_coverage,
        "load_coverage",
        lambda root, payload: {source_file: ({3, 4}, {12})},
    )

    assert python_changed_line_coverage.main() == 0

    output = capsys.readouterr().out
    assert "services/foo.py\t66.67%\t2/3" in output
    assert "uncovered: 12" in output
    assert "skipped-non-executable: 13" in output
    assert "TOTAL\t66.67%\t2/3" in output


def test_main_returns_non_zero_when_no_lines_are_measurable(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    source_file = (tmp_path / "services/foo.py").resolve()
    coverage_json = tmp_path / "coverage.json"
    coverage_json.write_text("{}")

    monkeypatch.setattr(
        python_changed_line_coverage,
        "parse_args",
        lambda: argparse.Namespace(
            coverage_json=str(coverage_json),
            diff_from="HEAD",
            files=[str(source_file)],
        ),
    )
    monkeypatch.setattr(python_changed_line_coverage, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        python_changed_line_coverage,
        "changed_lines",
        lambda root, diff_from, files: {source_file: {13}},
    )
    monkeypatch.setattr(
        python_changed_line_coverage,
        "load_coverage",
        lambda root, payload: {source_file: (set(), set())},
    )

    assert python_changed_line_coverage.main() == 1

    output = capsys.readouterr().out
    assert "services/foo.py\t100.00%\t0/0" in output
    assert "TOTAL\t100.00%\t0/0" in output
