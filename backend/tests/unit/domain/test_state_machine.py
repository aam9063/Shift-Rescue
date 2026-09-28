"""Unit tests for the rescue state machine (spec §4.2)."""

from contextlib import suppress

import pytest

from app.domain.state_machine import (
    SideEffect,
    State,
    StateMachineEvent,
    UndefinedTransition,
    transition,
)


def t(state: State, event: StateMachineEvent) -> tuple[State, tuple]:
    return transition(state, event)


class TestLegalTransitions:
    def test_open_plus_candidates_computed_goes_offering(self) -> None:
        new_state, effects = t(State.OPEN, StateMachineEvent.CANDIDATES_COMPUTED)
        assert new_state == State.OFFERING
        assert SideEffect.SEND_FIRST_WAVE in effects

    def test_open_without_candidates_escalates(self) -> None:
        new_state, effects = t(State.OPEN, StateMachineEvent.NO_ELIGIBLE_CANDIDATES)
        assert new_state == State.ESCALATED
        assert SideEffect.NOTIFY_MANAGER in effects

    def test_open_deadline_reached_escalates(self) -> None:
        """§5.4/§5.5: an absence that is never confirmed escalates when the
        deadline passes — it is never silently assumed."""
        new_state, effects = t(State.OPEN, StateMachineEvent.DEADLINE_REACHED)
        assert new_state == State.ESCALATED
        assert SideEffect.NOTIFY_MANAGER in effects

    def test_offering_unconditional_accept_covers(self) -> None:
        new_state, effects = t(State.OFFERING, StateMachineEvent.UNCONDITIONAL_ACCEPT)
        assert new_state == State.COVERED
        assert SideEffect.ASSIGN_SHIFT_IN_HRIS in effects
        assert SideEffect.CANCEL_PENDING_OFFERS in effects

    def test_offering_conditional_accept_awaits_approval(self) -> None:
        new_state, effects = t(State.OFFERING, StateMachineEvent.CONDITIONAL_ACCEPT)
        assert new_state == State.AWAITING_APPROVAL
        assert SideEffect.CREATE_APPROVAL_REQUEST in effects

    def test_offering_waves_exhausted_escalates(self) -> None:
        new_state, effects = t(State.OFFERING, StateMachineEvent.WAVES_EXHAUSTED)
        assert new_state == State.ESCALATED
        assert SideEffect.NOTIFY_MANAGER in effects

    def test_offering_deadline_reached_escalates(self) -> None:
        new_state, _ = t(State.OFFERING, StateMachineEvent.DEADLINE_REACHED)
        assert new_state == State.ESCALATED

    def test_awaiting_approval_approved_covers(self) -> None:
        new_state, effects = t(State.AWAITING_APPROVAL, StateMachineEvent.APPROVAL_APPROVED)
        assert new_state == State.COVERED
        assert SideEffect.ASSIGN_SHIFT_IN_HRIS in effects

    def test_awaiting_approval_approved_partial_covers_partially(self) -> None:
        new_state, _ = t(State.AWAITING_APPROVAL, StateMachineEvent.APPROVAL_APPROVED_PARTIAL)
        assert new_state == State.PARTIALLY_COVERED

    def test_awaiting_approval_rejected_resumes_offering(self) -> None:
        new_state, effects = t(State.AWAITING_APPROVAL, StateMachineEvent.APPROVAL_REJECTED)
        assert new_state == State.OFFERING
        assert SideEffect.RESUME_OFFERING in effects

    def test_awaiting_approval_timeout_resumes_offering(self) -> None:
        new_state, _ = t(State.AWAITING_APPROVAL, StateMachineEvent.APPROVAL_TIMEOUT)
        assert new_state == State.OFFERING

    def test_covered_withdrawal_reopens(self) -> None:
        new_state, effects = t(State.COVERED, StateMachineEvent.COVERING_WITHDREW)
        assert new_state == State.OFFERING
        assert SideEffect.UNASSIGN_SHIFT_IN_HRIS in effects
        assert SideEffect.RESUME_OFFERING in effects

    def test_escalated_manager_resolution_closes(self) -> None:
        new_state, _ = t(State.ESCALATED, StateMachineEvent.MANAGER_RESOLVED)
        assert new_state == State.CLOSED_BY_MANAGER

    def test_escalated_late_acceptance_awaits_approval(self) -> None:
        new_state, effects = t(State.ESCALATED, StateMachineEvent.LATE_ACCEPTANCE)
        assert new_state == State.AWAITING_APPROVAL
        assert SideEffect.NOTIFY_MANAGER in effects

    def test_offering_cancel_rescue_cancels(self) -> None:
        new_state, effects = t(State.OFFERING, StateMachineEvent.APPROVAL_APPROVED_CANCEL)
        assert new_state == State.CANCELLED
        assert SideEffect.SUPERSEDE_OFFERS in effects

    def test_awaiting_approval_cancel_rescue_cancels(self) -> None:
        new_state, effects = t(
            State.AWAITING_APPROVAL, StateMachineEvent.APPROVAL_APPROVED_CANCEL
        )
        assert new_state == State.CANCELLED
        assert SideEffect.SUPERSEDE_OFFERS in effects


class TestIllegalTransitions:
    @pytest.mark.parametrize(
        ("state", "event"),
        [
            (State.COVERED, StateMachineEvent.CANDIDATES_COMPUTED),
            (State.OPEN, StateMachineEvent.UNCONDITIONAL_ACCEPT),
            (State.OPEN, StateMachineEvent.APPROVAL_REJECTED),
            (State.ESCALATED, StateMachineEvent.CANDIDATES_COMPUTED),
            (State.CLOSED_BY_MANAGER, StateMachineEvent.UNCONDITIONAL_ACCEPT),
            (State.CANCELLED, StateMachineEvent.COVERING_WITHDREW),
            (State.PARTIALLY_COVERED, StateMachineEvent.CONDITIONAL_ACCEPT),
            (State.OFFERING, StateMachineEvent.MANAGER_RESOLVED),
        ],
    )
    def test_undefined_transitions_raise(self, state: State, event: StateMachineEvent) -> None:
        with pytest.raises(UndefinedTransition) as exc_info:
            transition(state, event)
        assert state.name in str(exc_info.value)
        assert event.name in str(exc_info.value)


def test_every_state_event_pair_is_covered_or_explicitly_illegal() -> None:
    """The machine is total: every (state, event) pair either transitions or raises."""
    for state in State:
        for event in StateMachineEvent:
            with suppress(UndefinedTransition):
                transition(state, event)
