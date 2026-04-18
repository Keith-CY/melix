from __future__ import annotations

import argparse
import importlib.util
import json
import runpy
import sys
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[3] / "scripts" / "validate_pr_evidence.py"
MODULE_SPEC = importlib.util.spec_from_file_location("validate_pr_evidence", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
validate_pr_evidence = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(validate_pr_evidence)


def test_load_body_text_reads_pull_request_body_from_event(tmp_path: Path) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps({"pull_request": {"body": "## Plan or Spec\n- docs/plans/example.md\n"}}),
        encoding="utf-8",
    )

    assert (
        validate_pr_evidence.load_body_text(
            argparse.Namespace(body_file=None, event_path=str(event_path))
        )
        == "## Plan or Spec\n- docs/plans/example.md\n"
    )


def test_load_body_text_reads_body_file_when_provided(tmp_path: Path) -> None:
    body_path = tmp_path / "body.md"
    body_path.write_text("## Plan or Spec\n- docs/plans/example.md\n", encoding="utf-8")

    assert (
        validate_pr_evidence.load_body_text(
            argparse.Namespace(body_file=str(body_path), event_path=None)
        )
        == "## Plan or Spec\n- docs/plans/example.md\n"
    )


def test_load_body_text_requires_an_input_source() -> None:
    with pytest.raises(ValueError, match="Either --body-file or --event-path is required."):
        validate_pr_evidence.load_body_text(
            argparse.Namespace(body_file=None, event_path=None)
        )


def test_load_body_text_rejects_non_string_pr_body(tmp_path: Path) -> None:
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps({"pull_request": {"body": ["not", "a", "string"]}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="pull_request.body must be a string."):
        validate_pr_evidence.load_body_text(
            argparse.Namespace(body_file=None, event_path=str(event_path))
        )


def test_validate_body_text_accepts_complete_sections() -> None:
    body = """
## Summary
- Add CI workflows.

## Plan or Spec
- docs/plans/2026-04-15-ci-github-actions.md

## Commands Run
```text
make py-test
make integration-test
```

## Coverage and Metrics
- N/A: CI configuration change only.

## Known Gaps
- Swift gate still pending a clean baseline run on GitHub-hosted macOS.
"""

    assert validate_pr_evidence.validate_body_text(body) == []


def test_validate_body_text_reports_missing_or_placeholder_sections() -> None:
    body = """
## Summary
- Add CI workflows.

## Plan or Spec
- TBD

## Commands Run

## Coverage and Metrics
- N/A

## Known Gaps
- TODO
"""

    errors = validate_pr_evidence.validate_body_text(body)

    assert "Section 'Plan or Spec' must not be placeholder text." in errors
    assert "Section 'Commands Run' is missing meaningful content." in errors
    assert "Section 'Coverage and Metrics' must explain N/A." in errors
    assert "Section 'Known Gaps' must not be placeholder text." in errors


def test_validate_body_text_rejects_empty_non_text_code_fence() -> None:
    body = """
## Plan or Spec
- docs/plans/2026-04-15-ci-failure-remediation.md

## Commands Run
```bash
```

## Coverage and Metrics
- N/A: workflow-only change.

## Known Gaps
- GitHub-hosted validation still required.
"""

    errors = validate_pr_evidence.validate_body_text(body)

    assert "Section 'Commands Run' is missing meaningful content." in errors


def test_validate_body_text_rejects_placeholder_prefixes() -> None:
    body = """
## Plan or Spec
- TBD: add final plan reference.

## Commands Run
```text
make py-test
```

## Coverage and Metrics
- N/A: validation-only change.

## Known Gaps
- TODO: fill later.
"""

    errors = validate_pr_evidence.validate_body_text(body)

    assert "Section 'Plan or Spec' must not be placeholder text." in errors
    assert "Section 'Known Gaps' must not be placeholder text." in errors


def test_validate_body_text_rejects_placeholder_comment_inside_commands_fence() -> None:
    body = """
## Plan or Spec
- docs/plans/2026-04-15-ci-failure-remediation.md

## Commands Run
```text
# paste the commands you ran and their outcomes
```

## Coverage and Metrics
- N/A: workflow-only change.

## Known Gaps
- GitHub validation still pending.
"""

    errors = validate_pr_evidence.validate_body_text(body)

    assert "Section 'Commands Run' is missing meaningful content." in errors


def test_main_returns_non_zero_when_body_is_invalid(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        validate_pr_evidence,
        "parse_args",
        lambda: argparse.Namespace(body_file=None, event_path="/tmp/event.json"),
    )
    monkeypatch.setattr(validate_pr_evidence, "load_body_text", lambda args: "## Summary\n- hi\n")

    assert validate_pr_evidence.main() == 1

    output = capsys.readouterr().out
    assert "Section 'Plan or Spec' is missing." in output
    assert "Section 'Commands Run' is missing." in output


def test_main_returns_zero_when_body_is_valid(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        validate_pr_evidence,
        "parse_args",
        lambda: argparse.Namespace(body_file="/tmp/body.md", event_path=None),
    )
    monkeypatch.setattr(
        validate_pr_evidence,
        "load_body_text",
        lambda args: """
## Plan or Spec
- docs/plans/2026-04-15-ci-failure-remediation.md

## Commands Run
```text
make proto-check
```

## Coverage and Metrics
- N/A: workflow-only change.

## Known Gaps
- GitHub validation still pending.
""",
    )

    assert validate_pr_evidence.main() == 0

    output = capsys.readouterr().out
    assert "PR evidence looks valid." in output


def test_script_entrypoint_exits_zero_for_valid_body_file(tmp_path: Path, monkeypatch, capsys) -> None:
    body_path = tmp_path / "body.md"
    body_path.write_text(
        """
## Plan or Spec
- docs/plans/2026-04-15-ci-failure-remediation.md

## Commands Run
```text
make proto-check
```

## Coverage and Metrics
- N/A: workflow-only change.

## Known Gaps
- GitHub validation still pending.
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["validate_pr_evidence.py", "--body-file", str(body_path)],
    )

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(MODULE_PATH), run_name="__main__")

    assert excinfo.value.code == 0
    assert "PR evidence looks valid." in capsys.readouterr().out
