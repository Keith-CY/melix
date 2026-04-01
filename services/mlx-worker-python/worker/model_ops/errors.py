from __future__ import annotations


class ModelOperationError(RuntimeError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        retriable: bool = False,
        details: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retriable = retriable
        self.details = dict(details or {})
