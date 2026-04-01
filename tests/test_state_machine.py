from app.sessions.models import SessionState
from app.sessions.state_machine import SessionStateMachine


def test_valid_state_transition_path() -> None:
    sm = SessionStateMachine()
    sm.transition_to(SessionState.DETECTING)
    sm.transition_to(SessionState.CAPTURING)
    sm.transition_to(SessionState.PREPARING_INPUT)
    assert sm.state == SessionState.PREPARING_INPUT


def test_invalid_transition_raises() -> None:
    sm = SessionStateMachine()
    try:
        sm.transition_to(SessionState.GENERATING)
        assert False, "Expected ValueError"
    except ValueError:
        assert True


def test_phase1_allows_preparing_to_cooldown() -> None:
    sm = SessionStateMachine()
    sm.transition_to(SessionState.DETECTING)
    sm.transition_to(SessionState.CAPTURING)
    sm.transition_to(SessionState.PREPARING_INPUT)
    sm.transition_to(SessionState.COOLDOWN)
    assert sm.state == SessionState.COOLDOWN
