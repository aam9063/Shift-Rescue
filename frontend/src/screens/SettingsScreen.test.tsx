import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { LocationSettings } from '../services/dashboardMock'
import { SettingsScreen } from './SettingsScreen'

const FIRST: LocationSettings = {
  agentPaused: false,
  rankingWeights: [
    { label: 'Coverage equity', level: 'high' },
    { label: 'Proximity (same zone)', level: 'medium' },
    { label: 'Extra-shift preference', level: 'medium' },
    { label: 'No overtime first', level: 'high' },
  ],
  waveSize: 3,
  waveIntervalMinutes: 10,
  quietStart: '23:00',
  quietEnd: '07:00',
}

const SECOND: LocationSettings = { ...FIRST, agentPaused: true, waveSize: 5 }

function renderScreen(client: QueryClient) {
  return render(
    <QueryClientProvider client={client}>
      <SettingsScreen />
    </QueryClientProvider>,
  )
}

describe('SettingsScreen draft sync', () => {
  it('follows the loaded settings when new query data arrives', async () => {
    // Live mode: the first paint can show defaults before the server payload
    // lands; the draft must follow the query data instead of staying seeded.
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    client.setQueryData(['settings'], FIRST)
    renderScreen(client)

    const toggle = await screen.findByRole('switch', { name: 'Pausar agente' })
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByLabelText('Candidates per wave')).toHaveValue(3)

    client.setQueryData(['settings'], SECOND)

    await waitFor(() => {
      expect(screen.getByRole('switch', { name: 'Pausar agente' })).toHaveAttribute(
        'aria-checked',
        'true',
      )
    })
    expect(screen.getByLabelText('Candidates per wave')).toHaveValue(5)
  })

  it('keeps the draft aligned when the query data does not change', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    client.setQueryData(['settings'], FIRST)
    renderScreen(client)

    await screen.findByRole('switch', { name: 'Pausar agente' })
    expect(screen.getByRole('switch', { name: 'Pausar agente' })).toHaveAttribute(
      'aria-checked',
      'false',
    )
  })
})
