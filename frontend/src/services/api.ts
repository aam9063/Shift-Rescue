import type {
  ApprovalRequest,
  ApprovalStatus,
  RescueCase,
  RescueDetail,
  Shift,
  SimulatorEmployee,
} from '../domain/types'
import type {
  AgentDecision,
  ChatMessage,
  Conversation,
  LocationSettings,
  OpsMetrics,
  SystemStatus,
} from './dashboardMock'
import { ApiError, apiFetch } from './apiClient'
import type { DashboardDataSource } from './mock'

/**
 * API-backed implementation of the dashboard data layer (spec §7.5). Every
 * method maps the wire payload to the existing frontend types — nothing with
 * an `any` leaks into components. The location is resolved once from
 * `GET /api/locations` (never a hardcoded id) and reused by every call.
 */

// Wire payloads (camelCase per frontend/src/domain/types.ts).

interface LocationWire {
  id: string
  name: string
  timezone: string
}

interface ConversationWire {
  id: string
  employeeId: string | null
  employeeName: string | null
  initials: string
  lastMessage: string
  lastMessageAt: string
  intent: string | null
  hasRescue: boolean
  rescueId: string | null
  rescueLabel: string
}

interface ChatMessageWire {
  id: string
  from: 'employee' | 'assistant'
  text: string
  createdAt: string
}

interface InterpretationRowWire {
  id: string
  time: string
  employeeName: string | null
  intent: string
  confidence: number
  model: string
  costUsd: number
  latencyMs: number
  validation: string
}

interface DailyCostWire {
  date: string
  costUsd: number
}

interface MetricsWire {
  costPerDay: DailyCostWire[]
  p50LatencyMs: number
  p95LatencyMs: number
  lowConfidencePct: number
  lowConfidenceTotal: number
  deliveryFailures: number
  stuckRescues: number
}

interface MutationAcceptedWire {
  status: string
  id: string
}

/** Rescue statuses the kanban and Ops treat as "active". */
const ACTIVE_RESCUE_STATUSES = new Set(['OPEN', 'OFFERING', 'AWAITING_APPROVAL', 'ESCALATED'])

/** Product latency target shown as the Ops caption; not served by the API. */
const LATENCY_TARGET_MS = 2500
/** Above this low-confidence rate the Ops screen raises a warning alert. */
const LOW_CONFIDENCE_ALERT_PCT = 10

// --- Location resolution (once, then reused) -------------------------------

let locationIdPromise: Promise<string> | null = null

export function getLocationId(): Promise<string> {
  locationIdPromise ??= apiFetch<LocationWire[]>('/api/locations')
    .then((locations) => {
      if (locations.length === 0) {
        throw new ApiError(404, 'No locations are configured for this account')
      }
      return locations[0].id
    })
    .catch((error: unknown) => {
      // Allow a retry after a failure instead of caching the rejection.
      locationIdPromise = null
      throw error
    })
  return locationIdPromise
}

/** Test hook: forget the cached location so each test resolves it again. */
export function resetLocationIdCache(): void {
  locationIdPromise = null
}

// --- DashboardDataSource implementation -------------------------------------

export class ApiDashboardDataSource implements DashboardDataSource {
  async getShifts(dayIso: string): Promise<Shift[]> {
    const locationId = await getLocationId()
    const from = encodeURIComponent(`${dayIso}T00:00:00Z`)
    const to = encodeURIComponent(`${dayIso}T23:59:59Z`)
    return apiFetch<Shift[]>(`/api/locations/${locationId}/shifts?from=${from}&to=${to}`)
  }

  async getActiveRescues(): Promise<RescueCase[]> {
    const locationId = await getLocationId()
    const rescues = await apiFetch<RescueCase[]>(`/api/rescues?location_id=${locationId}`)
    return rescues.filter((rescue) => ACTIVE_RESCUE_STATUSES.has(rescue.status))
  }

  async getRescueDetail(rescueId: string): Promise<RescueDetail> {
    return apiFetch<RescueDetail>(`/api/rescues/${encodeURIComponent(rescueId)}`)
  }

  async getPendingApprovals(): Promise<ApprovalRequest[]> {
    const locationId = await getLocationId()
    return apiFetch<ApprovalRequest[]>(
      `/api/approvals?status=pending&location_id=${locationId}`,
    )
  }

  async decideApproval(
    id: string,
    decision: Exclude<ApprovalStatus, 'pending' | 'expired'>,
    _decidedBy: string,
  ): Promise<void> {
    // The decision is enqueued by the API (202) and applied by the worker,
    // so the new state appears after the queries are invalidated and refetched.
    const action = decision === 'approved' ? 'approve' : 'reject'
    await apiFetch<MutationAcceptedWire>(`/api/approvals/${encodeURIComponent(id)}/${action}`, {
      method: 'POST',
    })
  }
}

// --- Second data layer (conversations, interpretations, ops, settings) ------

export async function fetchConversations(): Promise<Conversation[]> {
  const locationId = await getLocationId()
  const rows = await apiFetch<ConversationWire[]>(`/api/conversations?location_id=${locationId}`)
  return Promise.all(
    rows.map(async (row) => {
      const messages = await apiFetch<ChatMessageWire[]>(
        `/api/conversations/${encodeURIComponent(row.id)}/messages`,
      )
      return {
        employeeId: row.employeeId ?? row.id,
        employeeName: row.employeeName ?? 'Unknown',
        initials: row.initials,
        lastMessage: row.lastMessage,
        intent: row.intent ?? 'UNKNOWN',
        rescueLabel: row.rescueLabel,
        messages: messages.map((message) => ({ from: message.from, text: message.text })),
      }
    }),
  )
}

export async function fetchAgentDecisions(): Promise<AgentDecision[]> {
  const rows = await apiFetch<InterpretationRowWire[]>('/api/interpretations')
  return rows.map((row) => ({
    time: row.time,
    employeeName: row.employeeName ?? 'Unknown',
    intent: row.intent,
    confidence: row.confidence,
    model: row.model,
    costUsd: row.costUsd,
    latencyMs: row.latencyMs,
    validation: row.validation === 'OK' ? 'OK' : 'retry',
  }))
}

export async function fetchOpsMetrics(): Promise<OpsMetrics> {
  const locationId = await getLocationId()
  const [metrics, rescues] = await Promise.all([
    apiFetch<MetricsWire>(`/api/metrics?location_id=${locationId}`),
    apiFetch<RescueCase[]>(`/api/rescues?location_id=${locationId}`),
  ])
  const costHistory = metrics.costPerDay.map((entry) => entry.costUsd)
  const alerts: OpsMetrics['alerts'] = []
  if (metrics.stuckRescues > 0) {
    alerts.push({
      severity: 'error',
      title: 'Stuck rescue',
      detail: `${metrics.stuckRescues} active rescue${metrics.stuckRescues === 1 ? '' : 's'} with no events for over 15 min.`,
    })
  }
  if (metrics.deliveryFailures > 0) {
    alerts.push({
      severity: 'warning',
      title: 'Delivery failure',
      detail: `${metrics.deliveryFailures} message${metrics.deliveryFailures === 1 ? '' : 's'} could not be delivered.`,
    })
  }
  if (metrics.lowConfidencePct >= LOW_CONFIDENCE_ALERT_PCT) {
    alerts.push({
      severity: 'warning',
      title: 'High low-confidence rate',
      detail: `${metrics.lowConfidencePct}% of interpreted messages are below the confidence threshold.`,
    })
  }
  return {
    costToday: costHistory.length > 0 ? costHistory[costHistory.length - 1] : 0,
    rescuesCount: rescues.filter((rescue) => ACTIVE_RESCUE_STATUSES.has(rescue.status)).length,
    p95LatencyMs: metrics.p95LatencyMs,
    latencyTargetMs: LATENCY_TARGET_MS,
    lowConfidencePct: metrics.lowConfidencePct,
    lowConfidenceTotal: metrics.lowConfidenceTotal,
    stuckCount: metrics.stuckRescues,
    costHistory,
    alerts,
  }
}

export async function fetchSettings(): Promise<LocationSettings> {
  const locationId = await getLocationId()
  return apiFetch<LocationSettings>(`/api/locations/${locationId}/settings`)
}

export async function saveSettings(next: LocationSettings): Promise<LocationSettings> {
  const locationId = await getLocationId()
  return apiFetch<LocationSettings>(`/api/locations/${locationId}/settings`, {
    method: 'PATCH',
    body: JSON.stringify(next),
  })
}

/** Public endpoint: the degraded-mode banner works without a session. */
export function fetchSystemStatus(): Promise<SystemStatus> {
  return apiFetch<SystemStatus>('/api/status')
}

// --- Demo simulator (spec §7.5/§7.6) ------------------------------------------

interface DemoClockWire {
  now: string
  offsetSeconds: number
}

/** The roster for the Simulator screen: real employees with today's shift
 * and their conversation id (`GET /api/employees?location_id=`). */
export async function fetchSimulatorEmployees(): Promise<SimulatorEmployee[]> {
  const locationId = await getLocationId()
  return apiFetch<SimulatorEmployee[]>(`/api/employees?location_id=${locationId}`)
}

/** The real thread of one conversation (redacted bodies, spec §10). */
export async function fetchConversationThread(conversationId: string): Promise<ChatMessage[]> {
  const messages = await apiFetch<ChatMessageWire[]>(
    `/api/conversations/${encodeURIComponent(conversationId)}/messages`,
  )
  return messages.map((message) => ({ from: message.from, text: message.text }))
}

/** Send a message as an employee through the real pipeline: the API enqueues
 * the same task the Twilio webhook enqueues and answers 202. */
export async function sendSimulatorMessage(employeeId: string, text: string): Promise<string> {
  const ack = await apiFetch<MutationAcceptedWire>(
    `/dev/simulator/${encodeURIComponent(employeeId)}/messages`,
    { method: 'POST', body: JSON.stringify({ text }) },
  )
  return ack.id
}

/** Current virtual time and shared offset (`GET /dev/clock`). */
export async function fetchDemoClock(): Promise<DemoClockWire> {
  return apiFetch<DemoClockWire>('/dev/clock')
}

/** Move the shared demo clock; the backend also enqueues the reconcile sweep. */
export async function advanceDemoClock(seconds: number): Promise<DemoClockWire> {
  return apiFetch<DemoClockWire>('/dev/clock/advance', {
    method: 'POST',
    body: JSON.stringify({ seconds }),
  })
}
