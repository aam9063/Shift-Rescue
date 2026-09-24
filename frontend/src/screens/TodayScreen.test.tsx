import { screen } from '@testing-library/react'
import { renderWithProviders } from '../test/renderWithProviders'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { TodayScreen } from './TodayScreen'

// Matches the mock data day so countdowns are deterministic.
const NOW = new Date('2026-10-03T06:45:00+02:00')

describe('TodayScreen', () => {
  it('renders shift groups ordered kitchen-first with role labels', async () => {
    renderWithProviders(<TodayScreen now={NOW} />)
    const headings = await screen.findAllByRole('heading', { level: 2 })
    const texts = headings.map((h) => h.textContent)
    expect(texts.indexOf('Kitchen')).toBeLessThan(texts.indexOf('Floor'))
    expect(texts.indexOf('Floor')).toBeLessThan(texts.indexOf('Bar'))
    expect(texts).toContain('Cleaning')
    expect(texts).toContain('Supervisor')
  })

  it('renders each shift with its time range and status', async () => {
    renderWithProviders(<TodayScreen now={NOW} />)
    await screen.findAllByText('07:00 – 15:00')
    expect(screen.getAllByText(/Covered|Open|Absent|Scheduled/).length).toBeGreaterThan(0)
  })

  it('shows the assigned employee name when present', async () => {
    renderWithProviders(<TodayScreen now={NOW} />)
    await screen.findByText('María G.')
  })

  it('shows an empty state when there are no shifts', async () => {
    const { dataSource } = await import('../services/hooks')
    vi.spyOn(dataSource, 'getShifts').mockResolvedValue([])
    renderWithProviders(<TodayScreen now={NOW} />)
    expect(await screen.findByText('No shifts scheduled for today')).toBeInTheDocument()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })
})
