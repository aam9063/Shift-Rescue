import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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
  resetDemoClock,
  resetDemoData,
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
  resetDemoClock: vi.fn(),
  resetDemoData: vi.fn(),
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
    conversationId: 'conv_twilio_+34600000001',
  },
  {
    id: 'emp_2',
    displayName: 'Bruno Bar',
    roles: ['bar'],
    shiftStartsAt: null,
    shiftEndsAt: null,
    shiftStatus: null,
    conversationId: 'conv_twilio_+34600000002',
  },
  {
    id: 'emp_3',
    displayName: 'Iker Kitchen',
    roles: ['kitchen'],
    shiftStartsAt: '2026-10-03T14:00:00+00:00',
    shiftEndsAt: '2026-10-03T18:00:00+00:00',
    shiftStatus: 'scheduled',
    conversationId: 'conv_twilio_+34600000003',
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
  // The roster always advertises the deterministic thread id
  // (conv_twilio_<phone>); only Ana's thread has messages yet.
  vi.mocked(fetchConversationThread).mockImplementation(async (conversationId: string) =>
    conversationId === 'conv_twilio_+34600000001'
      ? [{ from: 'assistant', text: 'Hola Ana, contame que paso' }]
      : [],
  )
  vi.mocked(sendSimulatorMessage).mockResolvedValue('sim_test_1')
  vi.mocked(fetchDemoClock).mockResolvedValue({
    now: '2026-10-03T15:11:00+00:00',
    offsetSeconds: 0,
    clamped: false,
  })
  vi.mocked(advanceDemoClock).mockResolvedValue({
    now: '2026-10-03T15:21:00+00:00',
    offsetSeconds: 600,
    clamped: false,
  })
  vi.mocked(resetDemoClock).mockResolvedValue({
    now: '2026-10-03T15:11:00+00:00',
    offsetSeconds: 0,
    clamped: false,
  })
  vi.mocked(resetDemoData).mockResolvedValue({
    deleted: { rescue_case: 2, message: 5, offer: 3, shift: 14 },
    now: '2026-10-03T15:11:00+00:00',
    offsetSeconds: 0,
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
    expect(fetchConversationThread).toHaveBeenCalledWith('conv_twilio_+34600000001')
  })

  it('shows an honest empty thread for an employee who has not written yet', async () => {
    renderScreen()

    expect(await screen.findByText('Bruno Bar')).toBeInTheDocument()
    const frame = screen
      .getAllByTestId('employee-frame')
      .find((candidate) => within(candidate).queryByText('Bruno Bar') !== null)!
    expect(within(frame).getByText('No messages yet — write the first one.')).toBeInTheDocument()
    expect(fetchConversationThread).toHaveBeenCalledWith('conv_twilio_+34600000002')
  })

  it('shows the shared demo clock time', async () => {
    renderScreen()

    expect(await screen.findByText('15:11')).toBeInTheDocument()
  })

  it('labels each frame with the employee situation against the virtual clock', async () => {
    renderScreen()

    // Clock 15:11: Iker (14-18) is on shift now; Ana starts at 17:00; Bruno
    // has no shift today.
    expect(await screen.findByText('On shift now')).toBeInTheDocument()
    expect(screen.getByText('Starts at 17:00')).toBeInTheDocument()
    expect(screen.getByText('No shift today')).toBeInTheDocument()
  })

  it('orders the frames so the actionable employees come first', async () => {
    renderScreen()

    await screen.findByText('On shift now')
    const frames = screen.getAllByTestId('employee-frame')
    // The API order was Ana, Bruno, Iker; on-shift Iker must lead.
    expect(within(frames[0]).getByText('Iker Kitchen')).toBeInTheDocument()
    expect(within(frames[1]).getByText('Ana Floor')).toBeInTheDocument()
    expect(within(frames[2]).getByText('Bruno Bar')).toBeInTheDocument()
  })

  it('explains when nobody can report an absence right now', async () => {
    vi.mocked(fetchSimulatorEmployees).mockResolvedValue([
      {
        id: 'emp_1',
        displayName: 'Ana Floor',
        roles: ['floor'],
        shiftStartsAt: '2026-10-03T07:00:00+00:00',
        shiftEndsAt: '2026-10-03T15:00:00+00:00',
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
    ])
    renderScreen()

    expect(
      await screen.findByText(/Nobody is on shift right now/),
    ).toBeInTheDocument()
    expect(screen.getByText(/Reseed the demo data/)).toBeInTheDocument()
    expect(await screen.findByText('Ended at 15:00')).toBeInTheDocument()
  })

  it('shows the offset in human terms and warns prominently at an hour or more', async () => {
    vi.mocked(fetchDemoClock).mockResolvedValue({
      now: '2026-10-03T21:00:00+00:00',
      offsetSeconds: 23400,
      clamped: false,
    })
    renderScreen()

    // +6 h 30 m: the leftover-offset situation that motivated the feature.
    expect((await screen.findAllByText(/\+6 h 30 m ahead/)).length).toBeGreaterThan(0)
    // Prominent, impossible to miss: it states the consequence in plain
    // English and carries the fix inside it.
    const banner = screen.getByTestId('clock-shifted-banner')
    expect(banner).toHaveAttribute('role', 'alert')
    expect(
      within(banner).getByText(/employees who should be on shift read as finished/),
    ).toBeInTheDocument()
    expect(within(banner).getByRole('button', { name: 'Reset clock' })).toBeInTheDocument()
    // The small grey note is reserved for smaller offsets.
    expect(screen.queryByText(/The agent's "now" is shifted/)).not.toBeInTheDocument()
  })

  it('keeps the small note (and no banner) for offsets below an hour', async () => {
    vi.mocked(fetchDemoClock).mockResolvedValue({
      now: '2026-10-03T15:21:00+00:00',
      offsetSeconds: 600,
      clamped: false,
    })
    renderScreen()

    await screen.findByText(/The agent's "now" is shifted \+10 m ahead/)
    expect(screen.queryByTestId('clock-shifted-banner')).not.toBeInTheDocument()
    expect(screen.getByText(/The agent's "now" is shifted \+10 m ahead/)).toBeInTheDocument()
  })

  it('says when the endpoint clamped an advance at the ±6 h bound', async () => {
    vi.mocked(advanceDemoClock).mockResolvedValue({
      now: '2026-10-03T21:11:00+00:00',
      offsetSeconds: 21600,
      clamped: true,
    })
    const user = userEvent.setup()
    renderScreen()
    await screen.findByText('15:11')

    await user.click(screen.getByRole('button', { name: '+1h' }))

    expect(advanceDemoClock).toHaveBeenCalledWith(3600)
    expect(await screen.findByText(/the clock stops at ±6 h/)).toBeInTheDocument()
  })

  it('resets the demo clock from the prominent warning itself', async () => {
    vi.mocked(fetchDemoClock).mockResolvedValue({
      now: '2026-10-03T21:00:00+00:00',
      offsetSeconds: 23400,
      clamped: false,
    })
    const user = userEvent.setup()
    renderScreen()
    const banner = await screen.findByTestId('clock-shifted-banner')

    await user.click(within(banner).getByRole('button', { name: 'Reset clock' }))

    expect(resetDemoClock).toHaveBeenCalledTimes(1)
    // The reset answer puts the clock back on real time and dismisses the warning.
    expect(await screen.findByText(/on real time/)).toBeInTheDocument()
    expect(screen.queryByTestId('clock-shifted-banner')).not.toBeInTheDocument()
    expect(screen.queryByText(/\+6 h 30 m ahead/)).not.toBeInTheDocument()
  })

  it('resets the demo clock through the endpoint', async () => {
    vi.mocked(fetchDemoClock).mockResolvedValue({
      now: '2026-10-03T21:00:00+00:00',
      offsetSeconds: 23400,
      clamped: false,
    })
    const user = userEvent.setup()
    renderScreen()
    expect((await screen.findAllByText(/\+6 h 30 m ahead/)).length).toBeGreaterThan(0)

    // The control-panel control (the banner carries its own Reset action).
    await user.click(screen.getAllByRole('button', { name: 'Reset clock' })[0])

    expect(resetDemoClock).toHaveBeenCalledTimes(1)
    // The reset answer puts the clock back on real time.
    expect(await screen.findByText(/on real time/)).toBeInTheDocument()
    expect(screen.queryByText(/\+6 h 30 m ahead/)).not.toBeInTheDocument()
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

  // --- the agent's reply surfaces without a reload (feature manager-can-act T1)

  /** Drives the simulated flow under fake timers: sync fireEvent + explicit
   * timer advances, never userEvent (its waits couple to the timers). */
  function typeAndSend() {
    fireEvent.change(screen.getByLabelText('Message for Ana Floor'), {
      target: { value: 'no puedo venir hoy' },
    })
    fireEvent.click(screen.getByLabelText('Send message to Ana Floor'))
    return act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
  }

  function withFakeTimers() {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
  }

  it('surfaces the agent reply by polling the thread until it lands', async () => {
    withFakeTimers()
    try {
      renderScreen()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      expect(screen.getByText('Ana Floor')).toBeInTheDocument()

      await typeAndSend()

      // The agent answers in 10-15 s: the frame says so and blocks duplicates.
      expect(screen.getByText('the agent is replying…')).toBeInTheDocument()
      expect(screen.getByLabelText('Send message to Ana Floor')).toBeDisabled()

      // First poll (+3 s): no new outbound message yet, keep waiting.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3_000)
      })
      expect(screen.getByText('the agent is replying…')).toBeInTheDocument()

      vi.mocked(fetchConversationThread).mockResolvedValue([
        { from: 'assistant', text: 'Hola Ana, contame que paso' },
        { from: 'employee', text: 'no puedo venir hoy' },
        { from: 'assistant', text: 'Gracias, ya busco a alguien para cubrirte' },
      ])
      // Second poll: the reply is beyond the send-time baseline and shows up
      // in the thread without any manual reload.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3_000)
      })
      expect(screen.getByText('Gracias, ya busco a alguien para cubrirte')).toBeInTheDocument()
      expect(screen.queryByText('the agent is replying…')).not.toBeInTheDocument()
      expect(screen.getByLabelText('Send message to Ana Floor')).toBeEnabled()
    } finally {
      vi.useRealTimers()
    }
  })

  it('stops waiting once the polling bound is reached', async () => {
    withFakeTimers()
    try {
      renderScreen()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      await typeAndSend()
      expect(screen.getByText('the agent is replying…')).toBeInTheDocument()

      const callsAtSend = vi.mocked(fetchConversationThread).mock.calls.length
      // ~30 s bound: 10 polls at 3 s, then the frame stops waiting honestly.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(31_000)
      })
      expect(vi.mocked(fetchConversationThread).mock.calls.length).toBeLessThanOrEqual(
        callsAtSend + 10,
      )
      expect(screen.queryByText('the agent is replying…')).not.toBeInTheDocument()
      expect(screen.getByLabelText('Send message to Ana Floor')).toBeEnabled()
    } finally {
      vi.useRealTimers()
    }
  })

  it('stops polling when the screen unmounts', async () => {
    withFakeTimers()
    try {
      const view = renderScreen()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      await typeAndSend()

      const callsAtUnmount = vi.mocked(fetchConversationThread).mock.calls.length
      view.unmount()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(60_000)
      })
      expect(vi.mocked(fetchConversationThread).mock.calls.length).toBe(callsAtUnmount)
    } finally {
      vi.useRealTimers()
    }
  })

  it('advances the demo clock through the endpoint', async () => {
    const user = userEvent.setup()
    renderScreen()
    await screen.findByText('15:11')

    await user.click(screen.getByRole('button', { name: '+10 min' }))

    expect(advanceDemoClock).toHaveBeenCalledWith(600)
    expect(await screen.findByText('15:21')).toBeInTheDocument()
  })

  // --- one-click demo reset (feature demo-reset) ------------------------------

  it('asks for confirmation before resetting the demo data', async () => {
    const user = userEvent.setup()
    renderScreen()
    await screen.findByText('Ana Floor')

    await user.click(screen.getByRole('button', { name: 'Reset demo data' }))

    // The confirmation names what it deletes and admits it is destructive.
    expect(resetDemoData).not.toHaveBeenCalled()
    expect(screen.getByText(/every rescue, message and offer of the demo/)).toBeInTheDocument()
    expect(screen.getByText(/cannot be undone/)).toBeInTheDocument()
  })

  it('resets through the endpoint after confirmation and refreshes everything', async () => {
    const user = userEvent.setup()
    renderScreen()
    await screen.findByText('Ana Floor')
    const rosterCallsBefore = vi.mocked(fetchSimulatorEmployees).mock.calls.length

    await user.click(screen.getByRole('button', { name: 'Reset demo data' }))
    await user.click(screen.getByRole('button', { name: 'Yes, reset demo data' }))

    expect(resetDemoData).toHaveBeenCalledTimes(1)
    // The result line is the endpoint's honest summary.
    expect(
      await screen.findByText(
        'Deleted 2 rescues, 5 messages, 3 offers, 14 shifts. demo clock back on real time.',
      ),
    ).toBeInTheDocument()
    // Every board refetches: the roster (and with it the clock, threads and
    // rescues) is invalidated by the reset.
    await waitFor(() => {
      expect(vi.mocked(fetchSimulatorEmployees).mock.calls.length).toBeGreaterThan(
        rosterCallsBefore,
      )
    })
    expect(fetchDemoClock).toHaveBeenCalledTimes(2)
  })

  it('can cancel out of the reset confirmation', async () => {
    const user = userEvent.setup()
    renderScreen()
    await screen.findByText('Ana Floor')

    await user.click(screen.getByRole('button', { name: 'Reset demo data' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(resetDemoData).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Reset demo data' })).toBeInTheDocument()
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

  it('keeps the reset control usable and honest without a backend', async () => {
    vi.mocked(isMockMode).mockReturnValue(true)
    const user = userEvent.setup()
    renderScreen()

    await user.click(screen.getByRole('button', { name: 'Reset demo data' }))
    await user.click(screen.getByRole('button', { name: 'Yes, reset demo data' }))

    // Mock mode stores nothing: the line says so instead of faking a wipe.
    expect(resetDemoData).not.toHaveBeenCalled()
    expect(await screen.findByText('Nothing to delete. demo clock back on real time.')).toBeInTheDocument()
  })
})
