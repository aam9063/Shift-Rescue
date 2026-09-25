import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ApiDashboardDataSource,
  fetchAgentDecisions,
  fetchConversations,
  fetchOpsMetrics,
  fetchSettings,
  fetchSystemStatus,
  getLocationId,
  resetLocationIdCache,
  saveSettings,
} from '../api'
import { clearSession } from '../auth'
import type { LocationSettings } from '../dashboardMock'

interface StubbedResponse {
  body: unknown
  status?: number
}

/**
 * Queue of canned responses: each fetch call consumes the next one. The
 * location resolution call comes first in every sequence that needs it.
 */
function stubFetchSequence(responses: StubbedResponse[]): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn()
  for (const response of responses) {
    fetchMock.mockImplementationOnce(() =>
      Promise.resolve(
        new Response(JSON.stringify(response.body), {
          status: response.status ?? 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )
  }
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const LOCATIONS = [{ id: 'loc_la_terraza', name: 'La Terraza del Puerto', timezone: 'Europe/Madrid' }]

const SHIFTS_WIRE = [
  {
    id: 'shift_1',
    locationId: 'loc_la_terraza',
    role: 'floor',
    startsAt: '2026-10-03T13:00:00+00:00',
    endsAt: '2026-10-03T21:00:00+00:00',
    assigneeName: 'Iker M.',
    status: 'absent',
  },
]

const RESCUE_WIRE = {
  id: 'rescue_001',
  shiftId: 'shift_1',
  absentEmployeeName: 'Iker M.',
  status: 'OFFERING',
  deadlineAt: '2026-10-03T04:50:00+00:00',
  openedAt: '2026-10-03T04:40:00+00:00',
  waveCurrent: 2,
  waveTotal: 3,
  offerPreviews: [{ employeeName: 'Marta L.', status: 'pending' }],
}

const DETAIL_WIRE = {
  rescue: RESCUE_WIRE,
  shift: SHIFTS_WIRE[0],
  timeline: [
    {
      id: 'evt_1',
      rescueId: 'rescue_001',
      type: 'RESCUE_OPENED',
      actor: 'system',
      createdAt: '2026-10-03T04:40:00+00:00',
      interpretedByAi: null,
    },
  ],
  candidates: [
    {
      employeeId: 'emp_marta_l',
      name: 'Marta L.',
      score: 0.82,
      eligible: true,
      requiresApproval: false,
      reasons: [],
    },
    {
      employeeId: 'emp_pau_s',
      name: 'Pau S.',
      score: 0,
      eligible: false,
      requiresApproval: false,
      reasons: [{ code: 'MAX_WEEKLY_HOURS', message: 'Would exceed max weekly hours' }],
    },
  ],
  offers: [
    {
      id: 'offer_1',
      rescueId: 'rescue_001',
      employeeName: 'Marta L.',
      waveNumber: 1,
      status: 'PENDING',
      sentAt: '2026-10-03T04:41:00+00:00',
      expiresAt: '2026-10-03T04:51:00+00:00',
    },
  ],
}

const APPROVALS_WIRE = [
  {
    id: 'appr_001',
    rescueId: 'rescue_001',
    kind: 'overtime',
    status: 'pending',
    requestedAt: '2026-10-03T04:41:30+00:00',
    decidedBy: null,
    decidedAt: null,
    expiresAt: '2026-10-03T04:50:00+00:00',
    context: {
      employeeName: 'Bruno T.',
      shiftTime: '13:00-21:00',
      detail: 'Overtime needed to cover the shift',
    },
  },
]

const SETTINGS_WIRE: LocationSettings = {
  agentPaused: true,
  rankingWeights: [
    { label: 'Coverage equity', level: 'high' },
    { label: 'Proximity (same zone)', level: 'medium' },
  ],
  waveSize: 3,
  waveIntervalMinutes: 10,
  quietStart: '23:00',
  quietEnd: '07:00',
}

describe('ApiDashboardDataSource', () => {
  beforeEach(() => {
    resetLocationIdCache()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    clearSession()
  })

  it('getShifts resolves the location once and maps the shift payload', async () => {
    const fetchMock = stubFetchSequence([
      { body: LOCATIONS },
      { body: SHIFTS_WIRE },
    ])

    const shifts = await new ApiDashboardDataSource().getShifts('2026-10-03')

    expect(shifts).toEqual([
      {
        id: 'shift_1',
        locationId: 'loc_la_terraza',
        role: 'floor',
        startsAt: '2026-10-03T13:00:00+00:00',
        endsAt: '2026-10-03T21:00:00+00:00',
        assigneeName: 'Iker M.',
        status: 'absent',
      },
    ])
    expect(fetchMock.mock.calls[0][0]).toBe('/api/locations')
    expect(fetchMock.mock.calls[1][0]).toBe(
      '/api/locations/loc_la_terraza/shifts?from=2026-10-03T00%3A00%3A00Z&to=2026-10-03T23%3A59%3A59Z',
    )
  })

  it('getLocationId is memoized: /api/locations is fetched once and reused', async () => {
    const fetchMock = stubFetchSequence([{ body: LOCATIONS }])

    await expect(getLocationId()).resolves.toBe('loc_la_terraza')
    await expect(getLocationId()).resolves.toBe('loc_la_terraza')
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it('getActiveRescues keeps only active statuses', async () => {
    stubFetchSequence([
      { body: LOCATIONS },
      {
        body: [
          RESCUE_WIRE,
          { ...RESCUE_WIRE, id: 'rescue_done', status: 'COVERED' },
        ],
      },
    ])

    const rescues = await new ApiDashboardDataSource().getActiveRescues()

    expect(rescues.map((rescue) => rescue.id)).toEqual(['rescue_001'])
    expect(rescues[0].offerPreviews).toEqual([{ employeeName: 'Marta L.', status: 'pending' }])
  })

  it('getRescueDetail maps rescue, shift, timeline, candidates and offers', async () => {
    const fetchMock = stubFetchSequence([{ body: DETAIL_WIRE }])

    const detail = await new ApiDashboardDataSource().getRescueDetail('rescue_001')

    expect(fetchMock.mock.calls[0][0]).toBe('/api/rescues/rescue_001')

    expect(detail).toEqual({
      rescue: {
        id: 'rescue_001',
        shiftId: 'shift_1',
        absentEmployeeName: 'Iker M.',
        status: 'OFFERING',
        deadlineAt: '2026-10-03T04:50:00+00:00',
        openedAt: '2026-10-03T04:40:00+00:00',
        waveCurrent: 2,
        waveTotal: 3,
        offerPreviews: [{ employeeName: 'Marta L.', status: 'pending' }],
      },
      shift: SHIFTS_WIRE[0],
      timeline: [
        {
          id: 'evt_1',
          rescueId: 'rescue_001',
          type: 'RESCUE_OPENED',
          actor: 'system',
          createdAt: '2026-10-03T04:40:00+00:00',
          interpretedByAi: null,
        },
      ],
      candidates: DETAIL_WIRE.candidates,
      offers: DETAIL_WIRE.offers,
    })
  })

  it('getPendingApprovals requests status=pending for the resolved location', async () => {
    const fetchMock = stubFetchSequence([{ body: LOCATIONS }, { body: APPROVALS_WIRE }])

    const approvals = await new ApiDashboardDataSource().getPendingApprovals()

    expect(approvals).toEqual([
      {
        id: 'appr_001',
        rescueId: 'rescue_001',
        kind: 'overtime',
        status: 'pending',
        requestedAt: '2026-10-03T04:41:30+00:00',
        decidedBy: null,
        decidedAt: null,
        expiresAt: '2026-10-03T04:50:00+00:00',
        context: {
          employeeName: 'Bruno T.',
          shiftTime: '13:00-21:00',
          detail: 'Overtime needed to cover the shift',
        },
      },
    ])
    expect(fetchMock.mock.calls[1][0]).toBe('/api/approvals?status=pending&location_id=loc_la_terraza')
  })

  it('decideApproval POSTs to approve and accepts the 202 queued body', async () => {
    const fetchMock = stubFetchSequence([
      { body: { status: 'queued', id: 'appr_001' }, status: 202 },
    ])

    await expect(
      new ApiDashboardDataSource().decideApproval('appr_001', 'approved', 'manager_01'),
    ).resolves.toBeUndefined()

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/approvals/appr_001/approve')
    expect(init.method).toBe('POST')
  })

  it('decideApproval POSTs to reject for a rejected decision', async () => {
    const fetchMock = stubFetchSequence([
      { body: { status: 'queued', id: 'appr_001' }, status: 202 },
    ])

    await expect(
      new ApiDashboardDataSource().decideApproval('appr_001', 'rejected', 'manager_01'),
    ).resolves.toBeUndefined()

    expect(fetchMock.mock.calls[0][0]).toBe('/api/approvals/appr_001/reject')
  })

  it('surfaces a 401 as ApiError with the session cleared', async () => {
    stubFetchSequence([{ body: { detail: 'Invalid token' }, status: 401 }])

    await expect(new ApiDashboardDataSource().getShifts('2026-10-03')).rejects.toMatchObject({
      name: 'ApiError',
      status: 401,
    })
  })
})

describe('second data layer', () => {
  beforeEach(() => {
    resetLocationIdCache()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    clearSession()
  })

  it('fetchConversations merges the inbox with each conversation chat', async () => {
    const fetchMock = stubFetchSequence([
      { body: LOCATIONS },
      {
        body: [
          {
            id: 'conv_1',
            employeeId: 'emp_marta',
            employeeName: 'Marta L.',
            initials: 'ML',
            lastMessage: 'puedo pero llego a las 15:15',
            lastMessageAt: '2026-10-03T13:04:00+00:00',
            intent: 'OFFER_CONDITIONAL',
            hasRescue: true,
            rescueId: 'rescue_001',
            rescueLabel: 'Floor 15:00',
          },
          {
            id: 'conv_2',
            employeeId: null,
            employeeName: null,
            initials: '?',
            lastMessage: 'hola',
            lastMessageAt: '2026-10-03T14:00:00+00:00',
            intent: null,
            hasRescue: false,
            rescueId: null,
            rescueLabel: 'No rescue',
          },
        ],
      },
      {
        body: [
          { id: 'msg_1', from: 'assistant', text: 'Puedes cubrirlo?', createdAt: '2026-10-03T13:00:00+00:00', interpretation: null },
          { id: 'msg_2', from: 'employee', text: 'puedo pero llego a las 15:15', createdAt: '2026-10-03T13:04:00+00:00', interpretation: { intent: 'OFFER_CONDITIONAL', confidence: 0.78, model: 'claude-haiku-4.5' } },
        ],
      },
      {
        body: [
          { id: 'msg_3', from: 'employee', text: 'hola', createdAt: '2026-10-03T14:00:00+00:00', interpretation: null },
        ],
      },
    ])

    const conversations = await fetchConversations()

    expect(conversations).toEqual([
      {
        employeeId: 'emp_marta',
        employeeName: 'Marta L.',
        initials: 'ML',
        lastMessage: 'puedo pero llego a las 15:15',
        intent: 'OFFER_CONDITIONAL',
        rescueLabel: 'Floor 15:00',
        messages: [
          { from: 'assistant', text: 'Puedes cubrirlo?' },
          { from: 'employee', text: 'puedo pero llego a las 15:15' },
        ],
      },
      {
        employeeId: 'conv_2',
        employeeName: 'Unknown',
        initials: '?',
        lastMessage: 'hola',
        intent: 'UNKNOWN',
        rescueLabel: 'No rescue',
        messages: [{ from: 'employee', text: 'hola' }],
      },
    ])
    expect(fetchMock.mock.calls[2][0]).toBe('/api/conversations/conv_1/messages')
  })

  it('fetchAgentDecisions maps interpretation rows to AgentDecision', async () => {
    stubFetchSequence([
      {
        body: [
          {
            id: 'int_1',
            time: '2026-10-03T13:03:00+00:00',
            employeeName: 'Marta L.',
            intent: 'OFFER_ACCEPT',
            confidence: 0.92,
            model: 'nan/deepseek-v4',
            costUsd: 0.001,
            latencyMs: 410,
            validation: 'OK',
          },
          {
            id: 'int_2',
            time: '2026-10-03T13:07:00+00:00',
            employeeName: null,
            intent: 'UNCLEAR',
            confidence: 0.41,
            model: 'nan/deepseek-v4',
            costUsd: 0.001,
            latencyMs: 520,
            validation: 'retry',
          },
        ],
      },
    ])

    const decisions = await fetchAgentDecisions()

    expect(decisions).toEqual([
      {
        time: '2026-10-03T13:03:00+00:00',
        employeeName: 'Marta L.',
        intent: 'OFFER_ACCEPT',
        confidence: 0.92,
        model: 'nan/deepseek-v4',
        costUsd: 0.001,
        latencyMs: 410,
        validation: 'OK',
      },
      {
        time: '2026-10-03T13:07:00+00:00',
        employeeName: 'Unknown',
        intent: 'UNCLEAR',
        confidence: 0.41,
        model: 'nan/deepseek-v4',
        costUsd: 0.001,
        latencyMs: 520,
        validation: 'retry',
      },
    ])
  })

  it('fetchOpsMetrics maps the API metrics into the Ops screen shape', async () => {
    const fetchMock = stubFetchSequence([
      { body: LOCATIONS },
      {
        body: {
          costPerDay: [
            { date: '2026-10-02', costUsd: 3.1 },
            { date: '2026-10-03', costUsd: 4.12 },
          ],
          p50LatencyMs: 410,
          p95LatencyMs: 1980,
          lowConfidencePct: 6,
          lowConfidenceTotal: 340,
          deliveryFailures: 1,
          stuckRescues: 1,
        },
      },
      {
        body: [
          RESCUE_WIRE,
          { ...RESCUE_WIRE, id: 'rescue_done', status: 'COVERED' },
        ],
      },
    ])

    const metrics = await fetchOpsMetrics()

    expect(metrics).toEqual({
      costToday: 4.12,
      rescuesCount: 1,
      p95LatencyMs: 1980,
      latencyTargetMs: 2500,
      lowConfidencePct: 6,
      lowConfidenceTotal: 340,
      stuckCount: 1,
      costHistory: [3.1, 4.12],
      alerts: [
        { severity: 'error', title: 'Stuck rescue', detail: '1 active rescue with no events for over 15 min.' },
        { severity: 'warning', title: 'Delivery failure', detail: '1 message could not be delivered.' },
      ],
    })
    expect(fetchMock.mock.calls[1][0]).toBe('/api/metrics?location_id=loc_la_terraza')
  })

  it('fetchSettings and saveSettings round-trip the settings screen shape', async () => {
    // The location is resolved once and reused by the PATCH.
    const fetchMock = stubFetchSequence([
      { body: LOCATIONS },
      { body: SETTINGS_WIRE },
      { body: SETTINGS_WIRE },
    ])

    const settings = await fetchSettings()
    expect(settings).toEqual(SETTINGS_WIRE)

    const saved = await saveSettings(SETTINGS_WIRE)
    expect(saved).toEqual(SETTINGS_WIRE)
    const [url, init] = fetchMock.mock.calls[2] as [string, RequestInit]
    expect(url).toBe('/api/locations/loc_la_terraza/settings')
    expect(init.method).toBe('PATCH')
    expect(JSON.parse(init.body as string)).toEqual(SETTINGS_WIRE)
  })

  it('fetchSystemStatus reads the public status endpoint without a location call', async () => {
    const fetchMock = stubFetchSequence([
      {
        body: {
          degraded: true,
          reasons: ['llm_circuit_open'],
          details: ['El proveedor del LLM está fallando: modo degradado con parser determinista.'],
        },
      },
    ])

    const status = await fetchSystemStatus()

    expect(status).toEqual({
      degraded: true,
      reasons: ['llm_circuit_open'],
      details: ['El proveedor del LLM está fallando: modo degradado con parser determinista.'],
    })
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/status')
  })
})
