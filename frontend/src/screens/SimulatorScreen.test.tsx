import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { SimulatorEmployee } from '../domain/types'
import {
  advanceDemoClock,
  fetchConversationThread,
  fetchDemoClock,
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
})

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
