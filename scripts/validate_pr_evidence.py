from __future__ import annotations

import argparse
import json
from pathlib import Path


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
    for raw_line in body_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("```"):
            continue
        if line.startswith("- "):
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


def main() -> int:
    args = parse_args()
    body_text = load_body_text(args)
    errors = validate_body_text(body_text)
    if errors:
        for error in errors:
            print(error)
        return 1
    print("PR evidence looks valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
