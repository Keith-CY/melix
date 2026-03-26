from __future__ import annotations

from dataclasses import dataclass, field
from threading import Event


@dataclass
class RequestState:
    request_id: str
    cancel_event: Event = field(default_factory=Event)
    next_seq: int = 1
    emitted_tokens: list[str] = field(default_factory=list)

    def allocate_seq(self) -> int:
        value = self.next_seq
        self.next_seq += 1
        return value

    def append_token(self, token: str) -> None:
        self.emitted_tokens.append(token)

    @property
    def assistant_text(self) -> str:
        return "".join(self.emitted_tokens)
