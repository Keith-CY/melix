from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts/swift_changed_scope_coverage.py"
SPEC = importlib.util.spec_from_file_location(
    "swift_changed_scope_coverage",
    SCRIPT_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
swift_coverage = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = swift_coverage
SPEC.loader.exec_module(swift_coverage)


def test_changed_line_parser_counts_only_new_hunk_ranges() -> None:
    assert swift_coverage.parse_changed_line_numbers(
        """\
diff --git a/example.swift b/example.swift
@@ -1,2 +1,3 @@
@@ -20,4 +21,0 @@
@@ -40 +37 @@
"""
    ) == {1, 2, 3, 37}


def test_coverage_total_is_parser_compatible_and_never_rounds_up() -> None:
    assert swift_coverage.format_total(20, 1) == "TOTAL 20 1 95%"
    assert swift_coverage.format_total(1000, 51) == "TOTAL 1000 51 94%"
    assert swift_coverage.format_total(0, 0) == "TOTAL 0 0 100%"


def test_coverage_threshold_requires_measurable_ninety_five_percent() -> None:
    assert swift_coverage.meets_minimum(20, 19, 95.0) is True
    assert swift_coverage.meets_minimum(20, 18, 95.0) is False
    assert swift_coverage.meets_minimum(0, 0, 95.0) is False


def test_coverage_path_parser_is_typed_and_deduplicated() -> None:
    assert swift_coverage.parse_coverage_paths("") is None
    assert swift_coverage.parse_coverage_paths('"a.swift"') == {"a.swift"}
    assert swift_coverage.parse_coverage_paths('["a.swift", "a.swift"]') == {
        "a.swift"
    }
    with pytest.raises(ValueError, match="invalid"):
        swift_coverage.parse_coverage_paths("[")
    with pytest.raises(ValueError, match="must be a JSON list"):
        swift_coverage.parse_coverage_paths('{"a": 1}')


def test_nonmeasurable_exclusions_require_an_explicit_reason() -> None:
    assert swift_coverage.parse_exclusions(
        ["pkg/Sources/CLI/main.swift=executable target is not test-linked"]
    ) == {
        "pkg/Sources/CLI/main.swift": "executable target is not test-linked"
    }
    with pytest.raises(ValueError, match="PATH=REASON"):
        swift_coverage.parse_exclusions(["pkg/Sources/CLI/main.swift"])


def test_additional_profdata_specs_are_typed_resolved_and_repo_bounded(
    tmp_path: Path,
) -> None:
    first = tmp_path / ".build/e2e/a/debug/codecov/default.profdata"
    second = tmp_path / ".build/e2e/b/debug/codecov/default.profdata"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    assert swift_coverage.parse_additional_profdata_specs(
        ["pkg=.build/e2e/*/debug/codecov/default.profdata"]
    ) == {"pkg": (".build/e2e/*/debug/codecov/default.profdata",)}
    assert swift_coverage.resolve_additional_profdata(
        root=tmp_path,
        package_paths=["pkg"],
        raw_specs=["pkg=.build/e2e/*/debug/codecov/default.profdata"],
    ) == {"pkg": (first, second)}

    with pytest.raises(ValueError, match="PACKAGE=GLOB"):
        swift_coverage.parse_additional_profdata_specs(["pkg"])
    with pytest.raises(ValueError, match="unselected package"):
        swift_coverage.resolve_additional_profdata(
            root=tmp_path,
            package_paths=["pkg"],
            raw_specs=["other=.build/e2e/*/default.profdata"],
        )
    with pytest.raises(ValueError, match="stay within"):
        swift_coverage.resolve_additional_profdata(
            root=tmp_path,
            package_paths=["pkg"],
            raw_specs=["pkg=../outside.profdata"],
        )
    with pytest.raises(FileNotFoundError, match="matched no files"):
        swift_coverage.resolve_additional_profdata(
            root=tmp_path,
            package_paths=["pkg"],
            raw_specs=["pkg=.build/missing/*.profdata"],
        )


def test_package_path_filter_excludes_build_and_manifest_swift() -> None:
    package = "services/control-plane-swift"
    assert swift_coverage._is_package_swift_path(
        f"{package}/Sources/Agent.swift",
        package,
    )
    assert not swift_coverage._is_package_swift_path(
        f"{package}/.build/debug/Generated.swift",
        package,
    )
    assert not swift_coverage._is_package_swift_path(
        f"{package}/Package.swift",
        package,
    )


def test_root_package_filter_counts_root_sources_without_nested_packages() -> None:
    assert swift_coverage._is_package_swift_path(
        "Sources/MelixCLICore/LocalRuntimeFactory.swift",
        ".",
    )
    assert swift_coverage._is_package_swift_path(
        "tests/MelixCLITests/LocalRuntimeFactoryTests.swift",
        ".",
    )
    assert not swift_coverage._is_package_swift_path(
        "apps/macos-menubar/Sources/AppMain/AppMain.swift",
        ".",
    )
    assert not swift_coverage._is_package_swift_path(
        "services/control-plane-swift/Sources/AgentRuntime/Agent.swift",
        ".",
    )


def _completed(
    stdout: str = "",
    *,
    returncode: int = 0,
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_normalized_package_paths_validate_boundaries_and_manifests(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    package = root / "pkg"
    package.mkdir(parents=True)
    (package / "Package.swift").write_text("// package\n")
    assert swift_coverage._normalized_package_paths(
        root,
        ["pkg", "pkg"],
    ) == ("pkg",)

    with pytest.raises(ValueError, match="missing Package.swift"):
        swift_coverage._normalized_package_paths(root, ["missing"])
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "Package.swift").write_text("// outside\n")
    with pytest.raises(ValueError, match="outside the repository"):
        swift_coverage._normalized_package_paths(root, ["../outside"])


def test_candidate_path_discovery_covers_worktree_and_base_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "head"
    base = tmp_path / "base"
    root.mkdir()
    base.mkdir()
    results = iter(
        [
            _completed("pkg/Sources/Changed.swift\n"),
            _completed("pkg/Tests/Staged.swift\n"),
            _completed("pkg/Tests/New.swift\n"),
        ]
    )
    commands: list[list[str]] = []

    def fake_run(command, *, cwd, check=True):
        del cwd, check
        commands.append(list(command))
        return next(results)

    monkeypatch.setattr(swift_coverage, "_run", fake_run)
    assert swift_coverage._candidate_paths_from_worktree(
        root,
        ["pkg"],
        None,
    ) == {
        "pkg/Sources/Changed.swift",
        "pkg/Tests/Staged.swift",
        "pkg/Tests/New.swift",
    }
    assert commands[1][:4] == ["git", "diff", "--cached", "--name-only"]
    assert commands[2][:4] == ["git", "ls-files", "--others", "--exclude-standard"]

    monkeypatch.setattr(
        swift_coverage,
        "_run",
        lambda command, *, cwd, check=True: _completed(
            f'{root}/pkg/Sources/Changed.swift\n'
        ),
    )
    assert swift_coverage._candidate_paths_from_base(
        root,
        base,
        ["pkg"],
    ) == {"pkg/Sources/Changed.swift"}

    monkeypatch.setattr(
        swift_coverage,
        "_run",
        lambda command, *, cwd, check=True: _completed(
            returncode=2,
            stderr="bad diff",
        ),
    )
    with pytest.raises(RuntimeError, match="bad diff"):
        swift_coverage._candidate_paths_from_base(root, base, ["pkg"])

    commands.clear()
    results = iter(
        [
            _completed("pkg/Agent.swift\n"),
            _completed("pkg/NewAgent.swift\n"),
        ]
    )

    def diff_from_run(command, *, cwd, check=True):
        del cwd, check
        commands.append(list(command))
        return next(results)

    monkeypatch.setattr(swift_coverage, "_run", diff_from_run)
    assert swift_coverage._candidate_paths_from_worktree(
        root,
        ["pkg"],
        "origin/main",
    ) == {"pkg/Agent.swift", "pkg/NewAgent.swift"}
    assert "origin/main" in commands[0]
    assert commands[1][:4] == ["git", "ls-files", "--others", "--exclude-standard"]


def test_candidate_path_discovery_filters_allowlist_to_existing_swift(
    tmp_path: Path,
) -> None:
    source = tmp_path / "pkg/Sources/Agent.swift"
    source.parent.mkdir(parents=True)
    source.write_text("let value = 1\n")
    assert swift_coverage.discover_candidate_paths(
        root=tmp_path,
        base_root=None,
        package_paths=["pkg"],
        diff_from=None,
        coverage_paths=frozenset(
            {
                "pkg/Sources/Agent.swift",
                "pkg/Sources/Missing.swift",
                "outside.swift",
            }
        ),
    ) == ("pkg/Sources/Agent.swift",)


def test_changed_line_discovery_covers_base_ref_and_untracked_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "head"
    base = tmp_path / "base"
    source = root / "pkg/Agent.swift"
    old_source = base / "pkg/Agent.swift"
    source.parent.mkdir(parents=True)
    old_source.parent.mkdir(parents=True)
    source.write_text("one\ntwo\nthree\n")
    old_source.write_text("one\n")

    monkeypatch.setattr(
        swift_coverage,
        "_run",
        lambda command, *, cwd, check=True: _completed(
            "@@ -1 +1,3 @@\n",
            returncode=1,
        ),
    )
    assert swift_coverage._changed_lines_for_path(
        root=root,
        base_root=base,
        diff_from=None,
        rel_path="pkg/Agent.swift",
    ) == {1, 2, 3}

    commands: list[list[str]] = []

    def ref_run(command, *, cwd, check=True):
        del cwd, check
        commands.append(list(command))
        return _completed("@@ -1 +2 @@\n")

    monkeypatch.setattr(swift_coverage, "_run", ref_run)
    assert swift_coverage._changed_lines_for_path(
        root=root,
        base_root=None,
        diff_from="origin/main",
        rel_path="pkg/Agent.swift",
    ) == {2}
    assert "origin/main" in commands[0]

    commands.clear()
    results = iter([_completed(), _completed(returncode=1)])
    monkeypatch.setattr(
        swift_coverage,
        "_run",
        lambda command, *, cwd, check=True: (
            commands.append(list(command)) or next(results)
        ),
    )
    assert swift_coverage._changed_lines_for_path(
        root=root,
        base_root=None,
        diff_from=None,
        rel_path="pkg/Agent.swift",
    ) == {1, 2, 3}
    assert "HEAD" in commands[0]


def test_changed_line_base_diff_rejects_command_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "head/pkg/Agent.swift"
    source.parent.mkdir(parents=True)
    source.write_text("let value = 1\n")
    base = tmp_path / "base"
    base.mkdir()
    monkeypatch.setattr(
        swift_coverage,
        "_run",
        lambda command, *, cwd, check=True: _completed(
            returncode=2,
            stderr="diff failure",
        ),
    )
    with pytest.raises(RuntimeError, match="diff failure"):
        swift_coverage._changed_lines_for_path(
            root=tmp_path / "head",
            base_root=base,
            diff_from=None,
            rel_path="pkg/Agent.swift",
        )


def test_coverage_artifact_discovery_validates_each_required_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(FileNotFoundError, match="missing Swift code coverage"):
        swift_coverage._coverage_artifacts(tmp_path, "pkg")

    codecov = tmp_path / "pkg/.build/arm64/debug/codecov"
    codecov.mkdir(parents=True)
    (tmp_path / "pkg/.build/debug").symlink_to("arm64/debug")
    (codecov / "Package.json").write_text("{}")
    with pytest.raises(FileNotFoundError, match="missing profdata"):
        swift_coverage._coverage_artifacts(tmp_path, "pkg")

    (codecov / "default.profdata").write_bytes(b"profile")
    with pytest.raises(FileNotFoundError, match="expected one covered"):
        swift_coverage._coverage_artifacts(tmp_path, "pkg")

    binary = (
        codecov.parent
        / "DemoPackageTests.xctest/Contents/MacOS/DemoPackageTests"
    )
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"binary")
    assert swift_coverage._coverage_artifacts(tmp_path, "pkg") == (
        binary,
        codecov / "default.profdata",
    )

    isolated = tmp_path / "pkg/.build/native-focus/debug/codecov"
    isolated.mkdir(parents=True)
    (isolated / "Package.json").write_text("{}")
    (isolated / "default.profdata").write_bytes(b"isolated")
    isolated_binary = (
        isolated.parent
        / "DemoPackageTests.xctest/Contents/MacOS/DemoPackageTests"
    )
    isolated_binary.parent.mkdir(parents=True)
    isolated_binary.write_bytes(b"isolated-binary")
    assert swift_coverage._coverage_artifacts(tmp_path, "pkg") == (
        binary,
        codecov / "default.profdata",
    )

    additional = tmp_path / ".build/e2e/default.profdata"
    additional.parent.mkdir(parents=True)
    additional.write_bytes(b"additional")
    commands: list[list[str]] = []

    def merge_run(command, *, cwd, check=True):
        del cwd, check
        commands.append(list(command))
        Path(command[-1]).write_bytes(b"merged")
        return _completed()

    monkeypatch.setattr(swift_coverage, "_run", merge_run)
    merged = tmp_path / "merged"
    assert swift_coverage._coverage_artifacts(
        tmp_path,
        "pkg",
        additional_profdata=[additional],
        merge_root=merged,
    ) == (binary, merged / "pkg.profdata")
    assert commands == [
        [
            "xcrun",
            "llvm-profdata",
            "merge",
            "-sparse",
            str(codecov / "default.profdata"),
            str(additional),
            "-o",
            str(merged / "pkg.profdata"),
        ]
    ]


def test_line_count_parser_distinguishes_covered_missed_and_non_executable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        swift_coverage,
        "_run",
        lambda command, *, cwd, check=True: _completed(
            """\
  1|      3| let covered = true
  2|  #####| let missed = true
  3|       | }
  4|invalid| ignored
not coverage
"""
        ),
    )
    assert swift_coverage._line_counts(
        root=tmp_path,
        binary=tmp_path / "binary",
        profdata=tmp_path / "default.profdata",
        source=tmp_path / "Agent.swift",
    ) == {1: 3, 2: 0, 3: None, 4: None}


def test_empty_package_measurement_is_explicit(tmp_path: Path) -> None:
    assert swift_coverage.measure_package(
        root=tmp_path,
        base_root=None,
        package_path="pkg",
        diff_from=None,
        candidate_paths=[],
    ) == swift_coverage.PackageCoverage("pkg", 0, 0, 0, 0)


def test_package_measurement_aggregates_covered_and_missed_changed_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        swift_coverage,
        "_coverage_artifacts",
        lambda root, package: (tmp_path / "binary", tmp_path / "profile"),
    )
    monkeypatch.setattr(
        swift_coverage,
        "_changed_lines_for_path",
        lambda **kwargs: {1, 2, 3},
    )
    monkeypatch.setattr(
        swift_coverage,
        "_line_counts",
        lambda **kwargs: {1: 3, 2: 0, 3: None},
    )

    result = swift_coverage.measure_package(
        root=tmp_path,
        base_root=None,
        package_path="pkg",
        diff_from=None,
        candidate_paths=["pkg/Sources/Agent.swift", "outside.swift"],
    )

    assert result == swift_coverage.PackageCoverage("pkg", 1, 2, 1, 1)
    output = capsys.readouterr().out
    assert "measurable_changed_lines=[1, 2]" in output
    assert "covered_changed_lines=[1]" in output
    assert "missed_changed_lines=[2]" in output
    assert "changed_line_coverage=50.00%" in output


def test_package_measurement_reports_changed_file_missing_from_binary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        swift_coverage,
        "_coverage_artifacts",
        lambda root, package: (tmp_path / "binary", tmp_path / "profile"),
    )
    monkeypatch.setattr(
        swift_coverage,
        "_changed_lines_for_path",
        lambda **kwargs: {1, 2},
    )
    monkeypatch.setattr(
        swift_coverage,
        "_line_counts",
        lambda **kwargs: {},
    )

    result = swift_coverage.measure_package(
        root=tmp_path,
        base_root=None,
        package_path="pkg",
        diff_from=None,
        candidate_paths=["pkg/Sources/Unlinked.swift"],
    )

    assert result == swift_coverage.PackageCoverage(
        "pkg",
        1,
        0,
        0,
        0,
        ("pkg/Sources/Unlinked.swift",),
    )
    assert "coverage_linkage=missing" in capsys.readouterr().out


def test_automatic_base_root_supports_explicit_and_ci_layout(
    tmp_path: Path,
) -> None:
    root = tmp_path / "head"
    base = tmp_path / "base"
    root.mkdir()
    base.mkdir()
    assert swift_coverage._automatic_base_root(root, None, {}) is None
    assert swift_coverage._automatic_base_root(
        root,
        None,
        {"GITHUB_WORKSPACE": str(tmp_path)},
    ) == base
    assert swift_coverage._automatic_base_root(
        root,
        str(root),
        {},
    ) is None
    with pytest.raises(ValueError, match="does not exist"):
        swift_coverage._automatic_base_root(
            root,
            str(tmp_path / "missing"),
            {},
        )


def _stub_main_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    measurements: list[object],
) -> None:
    monkeypatch.setattr(swift_coverage, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        swift_coverage,
        "_normalized_package_paths",
        lambda root, packages: tuple(packages),
    )
    monkeypatch.setattr(
        swift_coverage,
        "_automatic_base_root",
        lambda root, explicit, env: None,
    )
    monkeypatch.setattr(
        swift_coverage,
        "discover_candidate_paths",
        lambda **kwargs: ("pkg/Agent.swift",),
    )
    iterator = iter(measurements)
    monkeypatch.setattr(
        swift_coverage,
        "measure_package",
        lambda **kwargs: next(iterator),
    )


@pytest.mark.parametrize(
    ("measurement", "expected"),
    (
        (swift_coverage.PackageCoverage("pkg", 0, 0, 0, 0), 0),
        (swift_coverage.PackageCoverage("pkg", 1, 0, 0, 0), 1),
        (swift_coverage.PackageCoverage("pkg", 1, 20, 18, 2), 1),
        (swift_coverage.PackageCoverage("pkg", 1, 20, 19, 1), 0),
    ),
)
def test_main_enforces_measurable_per_package_ninety_five_percent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    measurement: object,
    expected: int,
) -> None:
    _stub_main_dependencies(monkeypatch, tmp_path, [measurement])
    assert swift_coverage.main(
        ["--package", "pkg", "--minimum", "95"],
        env={},
    ) == expected


def test_main_aggregates_multiple_packages_and_rejects_invalid_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert swift_coverage.main(
        ["--package", "pkg", "--minimum", "101"],
        env={},
    ) == 2

    _stub_main_dependencies(
        monkeypatch,
        tmp_path,
        [
            swift_coverage.PackageCoverage("first", 1, 20, 20, 0),
            swift_coverage.PackageCoverage("second", 1, 20, 18, 2),
        ],
    )
    assert swift_coverage.main(
        ["--package", "first", "--package", "second"],
        env={},
    ) == 1

    monkeypatch.setattr(
        swift_coverage,
        "_normalized_package_paths",
        lambda root, packages: (_ for _ in ()).throw(ValueError("bad package")),
    )
    assert swift_coverage.main(["--package", "bad"], env={}) == 2


def test_main_rejects_unlinked_file_even_when_other_coverage_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _stub_main_dependencies(
        monkeypatch,
        tmp_path,
        [
            swift_coverage.PackageCoverage(
                "pkg",
                2,
                20,
                20,
                0,
                ("pkg/Sources/Unlinked.swift",),
            ),
        ],
    )

    assert swift_coverage.main(["--package", "pkg"], env={}) == 1
    assert "pkg/Sources/Unlinked.swift" in capsys.readouterr().err


def test_main_rejects_base_and_ref_together(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(swift_coverage, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        swift_coverage,
        "_normalized_package_paths",
        lambda root, packages: tuple(packages),
    )
    monkeypatch.setattr(
        swift_coverage,
        "_automatic_base_root",
        lambda root, explicit, env: tmp_path / "base",
    )
    assert swift_coverage.main(
        ["--package", "pkg", "--diff-from", "origin/main"],
        env={},
    ) == 2
