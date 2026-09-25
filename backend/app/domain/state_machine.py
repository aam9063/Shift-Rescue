"""Rescue state machine (spec §4.2).

Pure transition map: `transition(state, event) -> (new_state, side_effects)`.
Effects (send messages, schedule tasks, call the HRIS adapter) execute
OUTSIDE, after persisting the new state. Any transition not defined in the
map raises `UndefinedTransition` — never ignored silently (spec §4.2).
"""

from enum import StrEnum, auto
from typing import NamedTuple


class State(StrEnum):
    OPEN = "OPEN"
    OFFERING = "OFFERING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    COVERED = "COVERED"
    PARTIALLY_COVERED = "PARTIALLY_COVERED"
    ESCALATED = "ESCALATED"
    CLOSED_BY_MANAGER = "CLOSED_BY_MANAGER"
    CANCELLED = "CANCELLED"


class StateMachineEvent(StrEnum):
    CANDIDATES_COMPUTED = auto()
    NO_ELIGIBLE_CANDIDATES = auto()
    UNCONDITIONAL_ACCEPT = auto()
    CONDITIONAL_ACCEPT = auto()
    WAVES_EXHAUSTED = auto()
    DEADLINE_REACHED = auto()
    APPROVAL_APPROVED = auto()
    APPROVAL_APPROVED_PARTIAL = auto()
    APPROVAL_APPROVED_CANCEL = auto()
    APPROVAL_REJECTED = auto()
    APPROVAL_TIMEOUT = auto()
    COVERING_WITHDREW = auto()
    TECHNICAL_FAILURE = auto()
    MANAGER_RESOLVED = auto()
    LATE_ACCEPTANCE = auto()


class SideEffect(StrEnum):
    MARK_ABSENT_IN_HRIS = auto()
    SEND_FIRST_WAVE = auto()
    NOTIFY_MANAGER = auto()
    ASSIGN_SHIFT_IN_HRIS = auto()
    CANCEL_PENDING_OFFERS = auto()
    NOTIFY_EMPLOYEE_CONFIRMED = auto()
    CREATE_APPROVAL_REQUEST = auto()
    RESUME_OFFERING = auto()
    UNASSIGN_SHIFT_IN_HRIS = auto()
    SUPERSEDE_OFFERS = auto()


class UndefinedTransition(Exception):
    """Raised when the (state, event) pair has no defined transition."""

    def __init__(self, state: State, event: StateMachineEvent) -> None:
        self.state = state
        self.event = event
        super().__init__(f"Undefined transition: {state.name} + {event.name}")


class TransitionResult(NamedTuple):
    """Tuple per spec §4.2: transition(...) -> (new_state, side_effects)."""

    new_state: State
    side_effects: tuple[SideEffect, ...]


_TRANSITIONS: dict[tuple[State, StateMachineEvent], TransitionResult] = {
    # OPEN
    (State.OPEN, StateMachineEvent.CANDIDATES_COMPUTED): TransitionResult(
        State.OFFERING,
        (SideEffect.SEND_FIRST_WAVE,),
    ),
    (State.OPEN, StateMachineEvent.NO_ELIGIBLE_CANDIDATES): TransitionResult(
        State.ESCALATED,
        (SideEffect.NOTIFY_MANAGER,),
    ),
    # §5.4/§5.5: una ausencia sin confirmar nunca se da por hecha en silencio;
    # al vencer el plazo del rescate, el caso se escala al manager.
    (State.OPEN, StateMachineEvent.DEADLINE_REACHED): TransitionResult(
        State.ESCALATED,
        (SideEffect.NOTIFY_MANAGER,),
    ),
    # OFFERING
    (State.OFFERING, StateMachineEvent.UNCONDITIONAL_ACCEPT): TransitionResult(
        State.COVERED,
        (
            SideEffect.ASSIGN_SHIFT_IN_HRIS,
            SideEffect.CANCEL_PENDING_OFFERS,
            SideEffect.NOTIFY_EMPLOYEE_CONFIRMED,
            SideEffect.NOTIFY_MANAGER,
        ),
    ),
    (State.OFFERING, StateMachineEvent.CONDITIONAL_ACCEPT): TransitionResult(
        State.AWAITING_APPROVAL,
        (SideEffect.CREATE_APPROVAL_REQUEST, SideEffect.NOTIFY_MANAGER),
    ),
    (State.OFFERING, StateMachineEvent.APPROVAL_APPROVED_CANCEL): TransitionResult(
        State.CANCELLED,
        (SideEffect.SUPERSEDE_OFFERS, SideEffect.NOTIFY_MANAGER),
    ),
    (State.OFFERING, StateMachineEvent.WAVES_EXHAUSTED): TransitionResult(
        State.ESCALATED,
        (SideEffect.NOTIFY_MANAGER,),
    ),
    (State.OFFERING, StateMachineEvent.DEADLINE_REACHED): TransitionResult(
        State.ESCALATED,
        (SideEffect.NOTIFY_MANAGER,),
    ),
    # AWAITING_APPROVAL
    (State.AWAITING_APPROVAL, StateMachineEvent.APPROVAL_APPROVED): TransitionResult(
        State.COVERED,
        (
            SideEffect.ASSIGN_SHIFT_IN_HRIS,
            SideEffect.CANCEL_PENDING_OFFERS,
            SideEffect.NOTIFY_EMPLOYEE_CONFIRMED,
        ),
    ),
    (State.AWAITING_APPROVAL, StateMachineEvent.APPROVAL_APPROVED_PARTIAL): TransitionResult(
        State.PARTIALLY_COVERED,
        (
            SideEffect.ASSIGN_SHIFT_IN_HRIS,
            SideEffect.CANCEL_PENDING_OFFERS,
            SideEffect.NOTIFY_EMPLOYEE_CONFIRMED,
        ),
    ),
    (State.AWAITING_APPROVAL, StateMachineEvent.APPROVAL_APPROVED_CANCEL): TransitionResult(
        State.CANCELLED,
        (SideEffect.SUPERSEDE_OFFERS, SideEffect.NOTIFY_MANAGER),
    ),
    (State.AWAITING_APPROVAL, StateMachineEvent.APPROVAL_REJECTED): TransitionResult(
        State.OFFERING,
        (SideEffect.RESUME_OFFERING,),
    ),
    (State.AWAITING_APPROVAL, StateMachineEvent.APPROVAL_TIMEOUT): TransitionResult(
        State.OFFERING,
        (SideEffect.RESUME_OFFERING,),
    ),
    # COVERED
    (State.COVERED, StateMachineEvent.TECHNICAL_FAILURE): TransitionResult(
        State.ESCALATED,
        (SideEffect.NOTIFY_MANAGER,),
    ),
    (State.COVERED, StateMachineEvent.COVERING_WITHDREW): TransitionResult(
        State.OFFERING,
        (
            SideEffect.UNASSIGN_SHIFT_IN_HRIS,
            SideEffect.RESUME_OFFERING,
            SideEffect.NOTIFY_MANAGER,
        ),
    ),
    # ESCALATED
    (State.ESCALATED, StateMachineEvent.MANAGER_RESOLVED): TransitionResult(
        State.CLOSED_BY_MANAGER,
        (),
    ),
    (State.ESCALATED, StateMachineEvent.LATE_ACCEPTANCE): TransitionResult(
        State.AWAITING_APPROVAL,
        (SideEffect.NOTIFY_MANAGER, SideEffect.CREATE_APPROVAL_REQUEST),
    ),
}


def transition(state: State, event: StateMachineEvent) -> TransitionResult:
    result = _TRANSITIONS.get((state, event))
    if result is None:
        raise UndefinedTransition(state, event)
    return result
