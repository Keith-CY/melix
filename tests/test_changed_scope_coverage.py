from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "changed_scope_coverage.py"
MODULE_SPEC = importlib.util.spec_from_file_location("changed_scope_coverage", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
changed_scope_coverage = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(changed_scope_coverage)

PROBE_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "changed_scope_coverage_parse_probe.py"
PROBE_MODULE_SPEC = importlib.util.spec_from_file_location(
    "changed_scope_coverage_parse_probe", PROBE_MODULE_PATH
)
assert PROBE_MODULE_SPEC is not None
assert PROBE_MODULE_SPEC.loader is not None
changed_scope_coverage_parse_probe = importlib.util.module_from_spec(PROBE_MODULE_SPEC)
PROBE_MODULE_SPEC.loader.exec_module(changed_scope_coverage_parse_probe)


def test_parse_changed_lines_handles_multiple_files_and_hunks() -> None:
    diff_text = "\n".join(
        [
            "diff --git a/foo.py b/foo.py",
            "--- a/foo.py",
            "+++ b/foo.py",
            "@@ -0,0 +3,2 @@",
            "+alpha",
            "+beta",
            "@@ -10 +12 @@",
            "+gamma",
            "diff --git a/bar.py b/bar.py",
            "--- a/bar.py",
            "+++ b/bar.py",
            "@@ -5,2 +5,3 @@",
            " keep",
            "-old",
            "+new",
            "+extra",
        ]
    )

    changed = changed_scope_coverage._parse_changed_lines(diff_text)

    assert changed == {
        "foo.py": {3, 4, 12},
        "bar.py": {6, 7},
    }


def test_changed_lines_by_path_uses_one_batched_git_diff(monkeypatch, tmp_path: Path) -> None:
    observed_commands: list[list[str]] = []
    diff_text = "\n".join(
        [
            "diff --git a/foo.py b/foo.py",
            "--- a/foo.py",
            "+++ b/foo.py",
            "@@ -0,0 +2 @@",
            "+alpha",
            "diff --git a/bar.py b/bar.py",
            "--- a/bar.py",
            "+++ b/bar.py",
            "@@ -0,0 +5 @@",
            "+beta",
        ]
    )

    def fake_run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        observed_commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=diff_text, stderr="")

    monkeypatch.setattr(changed_scope_coverage.subprocess, "run", fake_run)

    changed = changed_scope_coverage._changed_lines_by_path(tmp_path, ["foo.py", "bar.py", "baz.py"])

    assert observed_commands == [["git", "diff", "--unified=0", "--", "foo.py", "bar.py", "baz.py"]]
    assert changed == {
        "foo.py": {2},
        "bar.py": {5},
        "baz.py": set(),
    }


def test_parse_changed_lines_ignores_no_newline_marker_and_keeps_line_numbers() -> None:
    diff_text = "\n".join(
        [
            "diff --git a/foo.py b/foo.py",
            "--- a/foo.py",
            "+++ b/foo.py",
            "@@ -1 +1,2 @@",
            "-old",
            "+new",
            "\\ No newline at end of file",
            "+tail",
        ]
    )

    changed = changed_scope_coverage._parse_changed_lines(diff_text)

    assert changed == {"foo.py": {1, 2}}


def test_parse_changed_lines_preserves_added_content_that_starts_with_diff_header_prefix() -> None:
    diff_text = "\n".join(
        [
            "diff --git a/foo.py b/foo.py",
            "--- a/foo.py",
            "+++ b/foo.py",
            "@@ -0,0 +1,2 @@",
            "++++not-a-header",
            "+---also-real-content",
        ]
    )

    changed = changed_scope_coverage._parse_changed_lines(diff_text)

    assert changed == {"foo.py": {1, 2}}


def test_parse_changed_lines_counts_blank_context_lines_with_prefix_dispatch() -> None:
    diff_text = "\n".join(
        [
            "diff --git a/foo.py b/foo.py",
            "--- a/foo.py",
            "+++ b/foo.py",
            "@@ -1,3 +1,4 @@",
            " context",
            "",
            "+inserted_after_blank",
        ]
    )

    changed = changed_scope_coverage._parse_changed_lines(diff_text)

    assert changed == {"foo.py": {3}}


def test_parse_changed_lines_uses_precompiled_patterns_and_prefix_marker_check(monkeypatch) -> None:
    def fail_module_level_regex(*args: object, **kwargs: object) -> object:  # pragma: no cover
        raise AssertionError("hot parser should use precompiled regex objects")

    monkeypatch.setattr(changed_scope_coverage.re, "match", fail_module_level_regex)
    monkeypatch.setattr(changed_scope_coverage.re, "search", fail_module_level_regex)

    diff_text = "\n".join(
        [
            "diff --git a/foo.py b/foo.py",
            "--- a/foo.py",
            "+++ b/foo.py",
            "@@ -1 +1,2 @@",
            "+new",
            " context",
            "+tail",
        ]
    )

    changed = changed_scope_coverage._parse_changed_lines(diff_text)

    assert changed == {"foo.py": {1, 3}}


def test_is_diff_file_marker_matches_only_real_file_markers() -> None:
    assert changed_scope_coverage._is_diff_file_marker("+++ b/foo.py")
    assert changed_scope_coverage._is_diff_file_marker("--- a/foo.py")
    assert changed_scope_coverage._is_diff_file_marker("+++ /dev/null")
    assert changed_scope_coverage._is_diff_file_marker("--- /dev/null")
    assert not changed_scope_coverage._is_diff_file_marker("++++not-a-header")
    assert not changed_scope_coverage._is_diff_file_marker("+---also-real-content")


def test_measurable_changed_lines_filters_blank_comment_and_unmeasured_lines(tmp_path: Path) -> None:
    source_path = tmp_path / "foo.py"
    source_path.write_text("first\n# comment\n\ncovered\nmissed\n", encoding="utf-8")
    coverage_payload = {
        "files": {
            "foo.py": {
                "executed_lines": [1, 4],
                "missing_lines": [5],
            }
        }
    }

    measurable, covered, missed = changed_scope_coverage._measurable_changed_lines(
        tmp_path,
        coverage_payload,
        "foo.py",
        {1, 2, 3, 4, 5},
    )

    assert measurable == [1, 4, 5]
    assert covered == [1, 4]
    assert missed == [5]


def test_parse_probe_reports_stable_parser_guardrails(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(changed_scope_coverage_parse_probe, "_load_changed_scope_module", lambda repo_root: changed_scope_coverage)
    monkeypatch.setattr(changed_scope_coverage_parse_probe.time, "perf_counter", iter([0.0, 0.01] * 12).__next__)

    metrics = changed_scope_coverage_parse_probe.run_probe(tmp_path)

    assert metrics["elapsed_ms_mean"] == 10.0
    assert metrics["file_count"] == 240.0
    assert metrics["changed_line_count"] == 7680.0
    assert metrics["line_count"] > metrics["changed_line_count"]


def test_parse_probe_loads_changed_scope_module() -> None:
    module = changed_scope_coverage_parse_probe._load_changed_scope_module(Path(__file__).resolve().parents[1])

    assert module._parse_changed_lines("diff --git a/foo.py b/foo.py\n@@ -0,0 +1 @@\n+new") == {"foo.py": {1}}


def test_parse_probe_main_prints_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        changed_scope_coverage_parse_probe,
        "run_probe",
        lambda repo_root: {"elapsed_ms_mean": 1.25, "changed_line_count": 2.0},
    )

    assert changed_scope_coverage_parse_probe.main() == 0

    assert json.loads(capsys.readouterr().out) == {"elapsed_ms_mean": 1.25, "changed_line_count": 2.0}


def test_main_reports_aggregate_coverage_for_multiple_paths(monkeypatch, tmp_path: Path, capsys) -> None:
    (tmp_path / "foo.py").write_text("covered\nmissed\n", encoding="utf-8")
    (tmp_path / "bar.py").write_text("covered\n", encoding="utf-8")
    coverage_json = tmp_path / "coverage.json"
    coverage_json.write_text(
        json.dumps(
            {
                "files": {
                    "foo.py": {"executed_lines": [1], "missing_lines": [2]},
                    "bar.py": {"executed_lines": [1], "missing_lines": []},
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "argv", ["changed_scope_coverage.py", "--coverage-json", str(coverage_json), "foo.py", "bar.py"])
    monkeypatch.setattr(changed_scope_coverage.Path, "cwd", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(
        changed_scope_coverage,
        "_changed_lines_by_path",
        lambda repo_root, rel_paths: {"foo.py": {1, 2}, "bar.py": {1}},
    )

    assert changed_scope_coverage.main() == 1

    output = capsys.readouterr().out
    assert "foo.py" in output
    assert "covered_changed_lines=[1]" in output
    assert "missed_changed_lines=[2]" in output
    assert "bar.py" in output
    assert "aggregate_measurable_changed_lines=3" in output
    assert "aggregate_covered_changed_lines=2" in output
    assert "aggregate_missed_changed_lines=1" in output
    assert "TOTAL 3 1 67%" in output
