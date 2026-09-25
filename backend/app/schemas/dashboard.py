"""Response schemas for the dashboard API.

Field names are the frontend contract (`frontend/src/domain/types.ts` plus the
shapes in `frontend/src/services/dashboardMock.ts`): camelCase JSON, ISO-8601
timestamps with offset. A renamed field must break the contract tests.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# --- shared helpers -----------------------------------------------------------


def iso_utc(value: datetime) -> str:
    """ISO-8601 with offset; naive values (SQLite round-trip) are UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


# --- auth ---------------------------------------------------------------------


class ManagerOut(BaseModel):
    id: str
    name: str
    email: str
    role: str
    locationIds: list[str]


class LoginResponse(BaseModel):
    accessToken: str
    tokenType: str
    expiresIn: int
    manager: ManagerOut


# --- locations and shifts (types.ts: Location-ish, Shift) ----------------------


class LocationOut(BaseModel):
    id: str
    name: str
    timezone: str


class ShiftOut(BaseModel):
    id: str
    locationId: str
    role: str
    startsAt: str
    endsAt: str
    assigneeName: str | None
    status: str


# --- settings (dashboardMock.ts: LocationSettings) -----------------------------


class RankingWeightOut(BaseModel):
    label: str
    level: str  # high | medium


class LocationSettingsOut(BaseModel):
    agentPaused: bool
    rankingWeights: list[RankingWeightOut]
    waveSize: int
    waveIntervalMinutes: int
    quietStart: str
    quietEnd: str


class LocationSettingsPatch(BaseModel):
    agentPaused: bool | None = None
    rankingWeights: list[RankingWeightOut] | None = None
    waveSize: int | None = None
    waveIntervalMinutes: int | None = None
    quietStart: str | None = None
    quietEnd: str | None = None


# --- rescues (types.ts: OfferPreview, RescueCase, RescueDetail) -----------------


class OfferPreviewOut(BaseModel):
    employeeName: str
    status: str  # pending | declined | accepted


class RescueCaseOut(BaseModel):
    id: str
    shiftId: str
    absentEmployeeName: str
    status: str
    deadlineAt: str
    openedAt: str | None = None
    waveCurrent: int | None = None
    waveTotal: int | None = None
    offerPreviews: list[OfferPreviewOut] | None = None


class AuditEventOut(BaseModel):
    id: str
    rescueId: str
    type: str
    actor: str
    createdAt: str
    interpretedByAi: bool | None = None


class ExclusionReasonOut(BaseModel):
    code: str
    message: str


class CandidateResultOut(BaseModel):
    employeeId: str
    name: str
    score: float
    eligible: bool
    requiresApproval: bool
    reasons: list[ExclusionReasonOut]


class OfferOut(BaseModel):
    id: str
    rescueId: str
    employeeId: str
    employeeName: str
    waveNumber: int
    status: str
    sentAt: str
    expiresAt: str


class RescueDetailOut(BaseModel):
    rescue: RescueCaseOut
    shift: ShiftOut
    timeline: list[AuditEventOut]
    candidates: list[CandidateResultOut]
    offers: list[OfferOut]


# --- approvals (types.ts: ApprovalRequest) -------------------------------------


class ApprovalContextOut(BaseModel):
    employeeName: str
    shiftTime: str
    detail: str | None = None


class ApprovalRequestOut(BaseModel):
    id: str
    rescueId: str
    kind: str
    status: str
    requestedAt: str
    decidedBy: str | None = None
    decidedAt: str | None = None
    expiresAt: str | None = None
    context: ApprovalContextOut


class MutationAcceptedOut(BaseModel):
    """Body of the 202 answers for enqueue-backed write endpoints."""

    status: str  # "queued"
    id: str


# --- conversations (dashboardMock.ts: Conversation / ChatMessage) ---------------


class InterpretationSummaryOut(BaseModel):
    intent: str
    confidence: float
    model: str


class ConversationMessageOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    from_: str = Field(alias="from")  # noqa: A002 - mock ChatMessage contract
    text: str  # always the stored redacted body (spec §10)
    createdAt: str
    interpretation: InterpretationSummaryOut | None = None


class ConversationOut(BaseModel):
    id: str
    employeeId: str | None
    employeeName: str | None
    initials: str
    lastMessage: str
    lastMessageAt: str
    intent: str | None
    hasRescue: bool
    rescueId: str | None
    rescueLabel: str


# --- interpretations (dashboardMock.ts: AgentDecision) --------------------------


class InterpretationRowOut(BaseModel):
    id: str
    time: str
    employeeName: str | None
    intent: str
    confidence: float
    model: str
    costUsd: float
    latencyMs: int
    validation: str  # "OK" | "retry"


class InterpretationDetailOut(InterpretationRowOut):
    promptVersion: str
    inputTokens: int
    outputTokens: int
    input: str  # redacted message body (spec §10)
    output: dict[str, Any]
    traceUrl: str | None


# --- metrics (spec §9.1/§9.2, ops screen) ----------------------------------------


class DailyCostOut(BaseModel):
    date: str
    costUsd: float


class MetricsOut(BaseModel):
    costPerDay: list[DailyCostOut]
    p50LatencyMs: float
    p95LatencyMs: float
    lowConfidencePct: float
    lowConfidenceTotal: int
    deliveryFailures: int
    stuckRescues: int
