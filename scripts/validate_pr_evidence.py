from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/mlx-worker-python"))

from worker.productization.benchmark_evaluation_report import validate_report_payload  # noqa: E402


REQUIRED_SECTIONS = (
    "Plan or Spec",
    "Commands Run",
    "Coverage and Metrics",
    "Known Gaps",
)
PLACEHOLDER_MARKERS = ("tbd", "todo", "_no response_")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate that a pull request body includes Melix evidence sections."
    )
    parser.add_argument(
        "--body-file",
        help="Path to a file containing the pull request body text.",
    )
    parser.add_argument(
        "--event-path",
        help="Path to a GitHub event JSON file containing pull_request.body.",
    )
    parser.add_argument(
        "--report-json",
        action="append",
        default=[],
        help="Optional structured report JSON path to validate with the PR evidence body.",
    )
    parser.add_argument(
        "--require-report-json",
        action="store_true",
        help="Require at least one --report-json path.",
    )
    return parser.parse_args()


def load_body_text(args: argparse.Namespace) -> str:
    if args.body_file:
        return Path(args.body_file).read_text(encoding="utf-8")
    if not args.event_path:
        raise ValueError("Either --body-file or --event-path is required.")
    payload = json.loads(Path(args.event_path).read_text(encoding="utf-8"))
    pull_request = payload.get("pull_request", {})
    body = pull_request.get("body", "")
    if not isinstance(body, str):
        raise ValueError("pull_request.body must be a string.")
    return body


def _extract_sections(body_text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current_section: str | None = None
    for line in body_text.splitlines():
        if line.startswith("## "):
            current_section = line[3:].strip()
            sections.setdefault(current_section, [])
            continue
        if current_section is not None:
            sections[current_section].append(line)
    return {
        name: "\n".join(lines).strip()
        for name, lines in sections.items()
    }


def _normalized_tokens(body_text: str) -> list[str]:
    cleaned = []
    in_fence = False
    for raw_line in body_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence and line.startswith("#"):
            continue
        if not in_fence and line.startswith("- "):
            line = line[2:].strip()
        cleaned.append(line)
    return cleaned


def _is_placeholder_token(token: str) -> bool:
    lowered = token.strip().lower()
    for marker in PLACEHOLDER_MARKERS:
        if lowered == marker:
            return True
        if lowered.startswith(marker) and len(lowered) > len(marker):
            if not lowered[len(marker)].isalnum():
                return True
    return False


def validate_body_text(body_text: str) -> list[str]:
    sections = _extract_sections(body_text)
    errors: list[str] = []
    for section_name in REQUIRED_SECTIONS:
        if section_name not in sections:
            errors.append(f"Section '{section_name}' is missing.")
            continue
        content = sections[section_name]
        tokens = _normalized_tokens(content)
        if not tokens:
            errors.append(f"Section '{section_name}' is missing meaningful content.")
            continue
        lowered = " ".join(tokens).lower()
        if any(_is_placeholder_token(token) for token in tokens):
            errors.append(f"Section '{section_name}' must not be placeholder text.")
            continue
        if section_name == "Coverage and Metrics" and lowered == "n/a":
            errors.append("Section 'Coverage and Metrics' must explain N/A.")
    return errors


def validate_report_json_paths(paths: list[str]) -> list[str]:
    errors: list[str] = []
    for path in paths:
        report_path = Path(path)
        if not report_path.is_file():
            errors.append(f"Report JSON is missing: {report_path}")
            continue
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"Report JSON could not be decoded: {report_path}: {exc.msg}")
            continue
        if not isinstance(payload, dict):
            errors.append(f"Report JSON must be an object: {report_path}")
            continue
        for error in validate_report_payload(payload):
            errors.append(f"{report_path}: {error}")
    return errors


def main() -> int:
    args = parse_args()
    body_text = load_body_text(args)
    errors = validate_body_text(body_text)
    report_json_paths = list(args.report_json or [])
    if args.require_report_json and not report_json_paths:
        errors.append("At least one --report-json path is required.")
    errors.extend(validate_report_json_paths(report_json_paths))
    if errors:
        for error in errors:
            print(error)
        return 1
    print("PR evidence looks valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
