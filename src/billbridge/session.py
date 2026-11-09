from dataclasses import dataclass, field

from billbridge.config import MAX_VERIFY_ATTEMPTS
from billbridge.models import Customer


@dataclass
class Session:
    session_id: str
    verified: bool = False
    customer: Customer | None = None
    failed_verifications: int = 0
    escalated: bool = False
    ticket_ref: str | None = None
    history: list[dict] = field(default_factory=list)
    tool_trace: list[str] = field(default_factory=list)
    allowed_cents: set[int] = field(default_factory=set)  # amounts tools have returned

    @property
    def locked(self) -> bool:
        return self.failed_verifications >= MAX_VERIFY_ATTEMPTS


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def get(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            self._sessions[session_id] = Session(session_id)
        return self._sessions[session_id]
