from __future__ import annotations

from threading import Lock


class ModelOpsConflictRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._held_scopes: dict[str, str] = {}

    def try_acquire(self, scope: str, operation: str) -> str | None:
        with self._lock:
            held_by = self._held_scopes.get(scope)
            if held_by is not None:
                return held_by
            self._held_scopes[scope] = operation
            return None

    def release(self, scope: str) -> None:
        with self._lock:
            self._held_scopes.pop(scope, None)
