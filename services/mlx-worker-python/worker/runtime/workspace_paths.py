from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from os import fspath
from pathlib import Path


_SENSITIVE_FILENAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        ".npmrc",
        ".netrc",
        ".pypirc",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
    }
)


@dataclass(frozen=True, slots=True)
class WorkspacePathResolution:
    operation: str
    workspace_root: Path
    requested_path: str
    resolved_path: Path
    allowed: bool
    refusal_reason: str = ""

    def receipt_fields(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "workspace_root": str(self.workspace_root),
            "requested_path": self.requested_path,
            "resolved_path": str(self.resolved_path),
            "allowed": self.allowed,
            "refusal_reason": self.refusal_reason,
        }


class WorkspacePathResolver:
    def __init__(
        self,
        workspace_root: str | Path,
        *,
        extra_sensitive_filenames: Iterable[str] = (),
    ) -> None:
        self._workspace_root = Path(workspace_root).expanduser().resolve(strict=False)
        self._sensitive_filenames = frozenset(
            name.casefold() for name in (*_SENSITIVE_FILENAMES, *extra_sensitive_filenames)
        )

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    def resolve(self, requested_path: str | Path, *, operation: str) -> WorkspacePathResolution:
        requested_text = fspath(requested_path)
        candidate = Path(requested_text).expanduser()
        if not candidate.is_absolute():
            candidate = self._workspace_root / candidate
        resolved_path = candidate.resolve(strict=False)

        refusal_reason = ""
        if not _is_relative_to(resolved_path, self._workspace_root):
            refusal_reason = "path_escapes_workspace"
        elif _has_sensitive_filename(resolved_path, self._workspace_root, self._sensitive_filenames):
            refusal_reason = "sensitive_path"

        return WorkspacePathResolution(
            operation=operation,
            workspace_root=self._workspace_root,
            requested_path=requested_text,
            resolved_path=resolved_path,
            allowed=not refusal_reason,
            refusal_reason=refusal_reason,
        )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _has_sensitive_filename(path: Path, root: Path, sensitive_filenames: frozenset[str]) -> bool:
    relative_parts = path.relative_to(root).parts
    return any(part.casefold() in sensitive_filenames for part in relative_parts)
