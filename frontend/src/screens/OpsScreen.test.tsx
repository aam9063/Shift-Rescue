import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/renderWithProviders'
import { systemStatusSource } from '../services/dashboardMock'
import { OpsScreen } from './OpsScreen'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('OpsScreen (degraded mode banner, spec §9.3)', () => {
  it('renders the operations KPIs and alerts when the system is healthy', async () => {
    renderWithProviders(<OpsScreen />)
    expect(await screen.findByText('Cost today')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows the degraded banner with the reasons from the status surface', async () => {
    vi.spyOn(systemStatusSource, 'get').mockResolvedValue({
      degraded: true,
      reasons: ['llm_circuit_open'],
      details: ['The LLM provider is failing: degraded mode with the deterministic parser.'],
    })

    renderWithProviders(<OpsScreen />)

    const banner = await screen.findByRole('alert')
    expect(banner).toHaveTextContent('Degraded mode')
    expect(banner).toHaveTextContent('The LLM provider is failing')
  })
})
