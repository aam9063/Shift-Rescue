import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/renderWithProviders'
import { RescueDetailScreen } from './RescueDetailScreen'

const NOW = new Date('2026-10-03T06:45:48+02:00')

describe('RescueDetailScreen (redesign per user mockup)', () => {
  it('renders the green hero band with back link, serif title and wave pill', async () => {
    const { container } = renderWithProviders(
      <RescueDetailScreen rescueId="rescue_001" now={NOW} onBack={vi.fn()} />,
    )
    await screen.findByText(/Iker M\./)
    const hero = container.querySelector('.bg-green-house')
    expect(hero).not.toBeNull()
    expect(screen.getByRole('button', { name: /Back to Today/ })).toBeInTheDocument()
    const title = screen.getByRole('heading', { level: 1 })
    expect(title).toHaveClass('font-serif')
    expect(title).toHaveTextContent('Floor · 15:00 – 23:00')
    expect(screen.getByText(/wave 2 of 3/)).toBeInTheDocument()
  })

  it('renders the giant MM:SS countdown with its caption in the hero', async () => {
    renderWithProviders(<RescueDetailScreen rescueId="rescue_001" now={NOW} onBack={vi.fn()} />)
    await screen.findByText('04:12')
    expect(screen.getByText(/minutes left/)).toBeInTheDocument()
  })

  it('renders the agent timeline chronologically with colored dots and AI badge', async () => {
    renderWithProviders(<RescueDetailScreen rescueId="rescue_001" now={NOW} onBack={vi.fn()} />)
    const timeline = await screen.findByRole('list', { name: 'Agent timeline' })
    const items = [...timeline.querySelectorAll('li')]
    const texts = items.map((li) => li.textContent ?? '')
    expect(texts.findIndex((t) => t.includes('Rescue opened')))
      .toBeLessThan(texts.findIndex((t) => t.includes('Offer declined')))
    expect(texts.findIndex((t) => t.includes('Offer declined')))
      .toBeLessThan(texts.findLastIndex((t) => t.includes('Offer sent')))
    // AI badge on the LLM-interpreted event
    expect(within(items[3]).getByText('AI')).toBeInTheDocument()
  })

  it('renders candidate cards with score and per-offer status, then excluded rows', async () => {
    renderWithProviders(<RescueDetailScreen rescueId="rescue_001" now={NOW} onBack={vi.fn()} />)
    await screen.findByText('Marta L.')
    expect(screen.getByText(/Score 0\.82/)).toBeInTheDocument()
    expect(screen.getAllByText(/no overtime/).length).toBeGreaterThan(0)
    expect(screen.getByText('declined')).toBeInTheDocument()
    expect(screen.getByText('Excluded')).toBeInTheDocument()
    expect(screen.getByText('MAX_WEEKLY_HOURS')).toBeInTheDocument()
    expect(screen.getByText('REST_VIOLATION')).toBeInTheDocument()
  })

  it('goes back to Today when the back button is pressed', async () => {
    const onBack = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(<RescueDetailScreen rescueId="rescue_001" now={NOW} onBack={onBack} />)
    await screen.findByText(/Iker M\./)
    await user.click(screen.getByRole('button', { name: /Back to Today/ }))
    expect(onBack).toHaveBeenCalledOnce()
  })
})
