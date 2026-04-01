"""Session state machine with explicit transition rules."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.sessions.models import SessionState


ALLOWED_TRANSITIONS: dict[SessionState, set[SessionState]] = {
    SessionState.IDLE: {SessionState.DETECTING, SessionState.ERROR},
    SessionState.DETECTING: {SessionState.CAPTURING, SessionState.IDLE, SessionState.ERROR},
    SessionState.CAPTURING: {SessionState.PREPARING_INPUT, SessionState.ERROR},
    SessionState.PREPARING_INPUT: {SessionState.GENERATING, SessionState.COOLDOWN, SessionState.ERROR},
    SessionState.GENERATING: {SessionState.COLLECTING_OUTPUTS, SessionState.ERROR},
    SessionState.COLLECTING_OUTPUTS: {SessionState.DISPLAYING, SessionState.ERROR},
    SessionState.DISPLAYING: {SessionState.COOLDOWN, SessionState.ERROR},
    SessionState.COOLDOWN: {SessionState.IDLE, SessionState.ERROR},
    SessionState.ERROR: {SessionState.COOLDOWN, SessionState.IDLE},
}


@dataclass
class SessionStateMachine:
    state: SessionState = SessionState.IDLE
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))

    def can_trigger_capture(self) -> bool:
        return self.state in {SessionState.IDLE, SessionState.DETECTING}

    def transition_to(self, new_state: SessionState) -> None:
        if new_state == self.state:
            return
        allowed = ALLOWED_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise ValueError(f"Invalid state transition: {self.state} -> {new_state}")
        self.logger.info("State transition: %s -> %s", self.state.value, new_state.value)
        self.state = new_state
