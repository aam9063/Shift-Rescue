import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Offer, RescueCase, RescueDetail, SimulatorEmployee } from '../domain/types'
import {
  advanceDemoClock,
  fetchActiveRescues,
  fetchConversationThread,
  fetchDemoClock,
  fetchRescueDetail,
  fetchSimulatorEmployees,
  sendSimulatorMessage,
} from '../services/api'
import { isMockMode } from '../services/dataSource'
import { CONVERSATIONS } from '../services/dashboardMock'
import { SimulatorScreen } from './SimulatorScreen'

vi.mock('../services/api', () => ({
  fetchSimulatorEmployees: vi.fn(),
  fetchConversationThread: vi.fn(),
  sendSimulatorMessage: vi.fn(),
  fetchDemoClock: vi.fn(),
  advanceDemoClock: vi.fn(),
  fetchActiveRescues: vi.fn(),
  fetchRescueDetail: vi.fn(),
}))

vi.mock('../services/dataSource', () => ({
  isMockMode: vi.fn(() => false),
  dataSource: {},
}))

const EMPLOYEES: SimulatorEmployee[] = [
  {
    id: 'emp_1',
    displayName: 'Ana Floor',
    roles: ['floor'],
    shiftStartsAt: '2026-10-03T17:00:00+00:00',
    shiftEndsAt: '2026-10-03T23:00:00+00:00',
    shiftStatus: 'absent',
    conversationId: 'conv_1',
  },
  {
    id: 'emp_2',
    displayName: 'Bruno Bar',
    roles: ['bar'],
    shiftStartsAt: null,
    shiftEndsAt: null,
    shiftStatus: null,
    conversationId: null,
  },
]

function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SimulatorScreen />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.mocked(isMockMode).mockReturnValue(false)
  vi.mocked(fetchSimulatorEmployees).mockResolvedValue(EMPLOYEES)
  vi.mocked(fetchConversationThread).mockResolvedValue([
    { from: 'assistant', text: 'Hola Ana, contame que paso' },
  ])
  vi.mocked(sendSimulatorMessage).mockResolvedValue('sim_test_1')
  vi.mocked(fetchDemoClock).mockResolvedValue({
    now: '2026-10-03T15:11:00+00:00',
    offsetSeconds: 0,
  })
  vi.mocked(advanceDemoClock).mockResolvedValue({
    now: '2026-10-03T15:21:00+00:00',
    offsetSeconds: 600,
  })
  vi.mocked(fetchActiveRescues).mockResolvedValue([])
  vi.mocked(fetchRescueDetail).mockRejectedValue(new Error('no rescue detail expected'))
})

// --- Acceptance-race scenario fixtures ---------------------------------------

const SCENARIO_RESCUE: RescueCase = {
  id: 'rescue_race',
  shiftId: 'shift_floor_01',
  absentEmployeeName: 'Ana Floor',
  status: 'OFFERING',
  deadlineAt: '2026-10-03T06:50:00+02:00',
  offerPreviews: [],
}

function offer(
  id: string,
  employeeId: string,
  employeeName: string,
  status: Offer['status'],
): Offer {
  return {
    id,
    rescueId: SCENARIO_RESCUE.id,
    employeeId,
    employeeName,
    waveNumber: 1,
    status,
    sentAt: '2026-10-03T06:41:00+02:00',
    expiresAt: '2026-10-03T06:51:00+02:00',
  }
}

function detailWith(offers: Offer[]): RescueDetail {
  return {
    rescue: SCENARIO_RESCUE,
    shift: {
      id: 'shift_floor_01',
      locationId: 'loc_1',
      role: 'floor',
      startsAt: '2026-10-03T15:00:00+02:00',
      endsAt: '2026-10-03T23:00:00+02:00',
      assigneeName: 'Ana Floor',
      status: 'absent',
    },
    timeline: [],
    candidates: [],
    offers,
  }
}

const TWO_PENDING = detailWith([
  offer('offer_1', 'emp_1', 'Ana Floor', 'PENDING'),
  offer('offer_2', 'emp_2', 'Bruno Bar', 'PENDING'),
])

const ONE_PENDING = detailWith([offer('offer_1', 'emp_1', 'Ana Floor', 'PENDING')])

function scenarioButton() {
  return screen.getByRole('button', { name: 'Run scenario: two candidates accept at once' })
}

describe('SimulatorScreen (spec §7.6, real data)', () => {
  it('renders the real employee list with their real thread', async () => {
    renderScreen()

    expect(await screen.findByText('Ana Floor')).toBeInTheDocument()
    expect(screen.getByText('Bruno Bar')).toBeInTheDocument()
    // The thread of the first employee's real conversation.
    expect(await screen.findByText('Hola Ana, contame que paso')).toBeInTheDocument()
    expect(fetchConversationThread).toHaveBeenCalledWith('conv_1')
  })

  it('shows the shared demo clock time', async () => {
    renderScreen()

    expect(await screen.findByText('15:11')).toBeInTheDocument()
  })

  it('sends a message through the simulator endpoint', async () => {
    const user = userEvent.setup()
    renderScreen()
    await screen.findByText('Ana Floor')

    await user.type(screen.getByLabelText('Message for Ana Floor'), 'no puedo venir hoy')
    await user.click(screen.getByLabelText('Send message to Ana Floor'))

    await waitFor(() => {
      expect(sendSimulatorMessage).toHaveBeenCalledWith('emp_1', 'no puedo venir hoy')
    })
  })

  it('advances the demo clock through the endpoint', async () => {
    const user = userEvent.setup()
    renderScreen()
    await screen.findByText('15:11')

    await user.click(screen.getByRole('button', { name: '+10 min' }))

    expect(advanceDemoClock).toHaveBeenCalledWith(600)
    expect(await screen.findByText('15:21')).toBeInTheDocument()
  })

  it('disables the scenario and says why when no rescue is offering', async () => {
    renderScreen()

    expect(await screen.findByText(/No active rescue is offering right now/)).toBeInTheDocument()
    expect(scenarioButton()).toBeDisabled()
    expect(sendSimulatorMessage).not.toHaveBeenCalled()
  })

  it('disables the scenario when the rescue has fewer than two pending offers', async () => {
    vi.mocked(fetchActiveRescues).mockResolvedValue([SCENARIO_RESCUE])
    vi.mocked(fetchRescueDetail).mockResolvedValue(ONE_PENDING)
    renderScreen()

    expect(await screen.findByText(/fewer than two pending offers to race/)).toBeInTheDocument()
    expect(scenarioButton()).toBeDisabled()
    expect(sendSimulatorMessage).not.toHaveBeenCalled()
  })

  it('fires both acceptances together and explains what to watch', async () => {
    vi.mocked(fetchActiveRescues).mockResolvedValue([SCENARIO_RESCUE])
    vi.mocked(fetchRescueDetail).mockResolvedValue(TWO_PENDING)
    // Deferred promises: neither send resolves until the test allows it, so
    // any sequential implementation (await then send) would show one call.
    let resolveFirst!: (id: string) => void
    let resolveSecond!: (id: string) => void
    vi.mocked(sendSimulatorMessage).mockImplementation(
      (employeeId) =>
        new Promise((resolve) => {
          if (employeeId === 'emp_1') {
            resolveFirst = resolve
          } else {
            resolveSecond = resolve
          }
        }),
    )
    const user = userEvent.setup()
    renderScreen()

    expect(await screen.findByText(/exactly one candidate keeps the shift/)).toBeInTheDocument()
    expect(scenarioButton()).toBeEnabled()

    await user.click(scenarioButton())

    // Both sends were started before either resolved: a real race.
    expect(sendSimulatorMessage).toHaveBeenCalledTimes(2)
    expect(sendSimulatorMessage).toHaveBeenCalledWith('emp_1', 'sí')
    expect(sendSimulatorMessage).toHaveBeenCalledWith('emp_2', 'sí')
    expect(screen.getByRole('button', { name: 'Running scenario…' })).toBeDisabled()

    await act(async () => {
      resolveFirst('sim_1')
      resolveSecond('sim_2')
    })

    expect(
      await screen.findByText(/Done: one candidate should now hold the shift/),
    ).toBeInTheDocument()
    // The rescue/shift/approval boards refetch to show the outcome.
    await waitFor(() => {
      expect(fetchActiveRescues).toHaveBeenCalledTimes(2)
    })
  })

  it('keeps the scenario unavailable and explained behind VITE_USE_MOCK', async () => {
    vi.mocked(isMockMode).mockReturnValue(true)
    renderScreen()

    expect(await screen.findByText(/runs in live mode/)).toBeInTheDocument()
    expect(scenarioButton()).toBeDisabled()
    expect(fetchActiveRescues).not.toHaveBeenCalled()
  })
})

describe('SimulatorScreen behind VITE_USE_MOCK', () => {
  it('still renders the mock conversations and a local clock', async () => {
    vi.mocked(isMockMode).mockReturnValue(true)
    renderScreen()

    expect(await screen.findByText(CONVERSATIONS[0].employeeName)).toBeInTheDocument()
    expect(await screen.findByText(CONVERSATIONS[0].messages[0].text)).toBeInTheDocument()
    // The mock clock starts at its documented demo time.
    expect(screen.getByText('15:11')).toBeInTheDocument()
  })
})
