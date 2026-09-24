import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/renderWithProviders'
import { RescueDetailScreen } from './RescueDetailScreen'

const NOW = new Date('2026-10-03T06:45:00+02:00')

describe('RescueDetailScreen', () => {
  it('goes back to Today when the back button is pressed', async () => {
    const onBack = vi.fn()
    renderWithProviders(<RescueDetailScreen rescueId="rescue_001" now={NOW} onBack={onBack} />)
    await screen.findByText(/Lucía F\./)
    await userEvent.click(screen.getByRole('button', { name: /Back to Today/ }))
    expect(onBack).toHaveBeenCalledOnce()
  })

  it('renders the rescue summary with the absent employee and the affected shift', async () => {
    renderWithProviders(<RescueDetailScreen rescueId="rescue_001" now={NOW} onBack={vi.fn()} />)
    await screen.findByText(/Lucía F\./)
    expect(screen.getByText(/07:00 – 15:00/)).toBeInTheDocument()
    expect(screen.getByText(/Offering shift to candidates/)).toBeInTheDocument()
  })

  it('renders the timeline in chronological order with English labels', async () => {
    renderWithProviders(<RescueDetailScreen rescueId="rescue_001" now={NOW} onBack={vi.fn()} />)
    const timeline = await screen.findByRole('list', { name: 'Rescue timeline' })
    const items = [...timeline.querySelectorAll('li')]
    const texts = items.map((li) => li.textContent ?? '')
    expect(texts.some((t) => t.includes('Rescue opened'))).toBe(true)
    expect(texts.findIndex((t) => t.includes('Rescue opened')))
      .toBeLessThan(texts.findIndex((t) => t.includes('Offer declined')))
  })

  it('renders candidates ordered by score with exclusion reasons', async () => {
    renderWithProviders(<RescueDetailScreen rescueId="rescue_001" now={NOW} onBack={vi.fn()} />)
    await screen.findByText('María G.')
    expect(screen.getByText(/7\.5h rest/)).toBeInTheDocument()
    expect(screen.getByText(/Office staff cannot cover floor shifts/)).toBeInTheDocument()
    expect(screen.getByText(/Would exceed contracted 30h weekly hours/)).toBeInTheDocument()
  })

  it('renders offers with their wave and status', async () => {
    renderWithProviders(<RescueDetailScreen rescueId="rescue_001" now={NOW} onBack={vi.fn()} />)
    await screen.findAllByText(/Wave 1/)
    expect(screen.getAllByText(/Pending|Declined/).length).toBeGreaterThanOrEqual(2)
  })
})
