import { screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/renderWithProviders'
import { EvalsScreen } from './EvalsScreen'
import { fetchEvalSummary } from '../services/api'
import { isMockMode } from '../services/dataSource'
import type { EvalRunSummary } from '../services/dashboardMock'

// The screen reaches the API only through the hooks' data layer; the tests
// mock the seam the same way SimulatorScreen does: api + dataSource.
vi.mock('../services/api', () => ({
  fetchEvalSummary: vi.fn(),
}))

vi.mock('../services/dataSource', () => ({
  isMockMode: vi.fn(() => true),
}))

const LIVE_SUMMARY: EvalRunSummary & { hasRuns: boolean } = {
  hasRuns: true,
  passed: true,
  commit: 'dead123',
  ranAgo: '12 minutes ago',
  accuracyHistory: [0.9, 0.93, 0.9935],
  threshold: 0.92,
  latestAccuracy: 0.9935,
  scenarios: [
    { id: 'quick_coverage', passed: true },
    { id: 'no_candidates', passed: false },
  ],
  models: [{ name: 'gpt-4o-mini', accuracy: 0.9935, costPerMessage: '$0.0010' }],
  invariantViolations: 1,
}

function liveSummary(overrides: Partial<typeof LIVE_SUMMARY> = {}) {
  return { ...LIVE_SUMMARY, ...overrides }
}

/**
 * Responsive contract (DESIGN.md §8 gutter/column scale). jsdom evaluates no
 * media queries, so this test pins the CSS-class contract of the grid; the
 * parent verifies the visual result at 768px (tablet) and 1440px.
 */
describe('EvalsScreen responsive contract', () => {
  beforeEach(() => {
    // Hermetic default: the mock fixture (VITE_USE_MOCK=true in tests).
    vi.mocked(isMockMode).mockReturnValue(true)
  })

  it('steps the results grid 1 -> 2 -> 5 columns across breakpoints', async () => {
    renderWithProviders(<EvalsScreen />)

    const grid = await screen.findByTestId('evals-grid')
    expect(grid).toHaveClass('grid-cols-1', 'md:grid-cols-2', 'lg:grid-cols-5')
  })
})

describe('EvalsScreen live summary', () => {
  beforeEach(() => {
    vi.mocked(fetchEvalSummary).mockReset()
    vi.mocked(isMockMode).mockReturnValue(false)
  })

  it('renders the live recorded summary', async () => {
    vi.mocked(fetchEvalSummary).mockResolvedValue(liveSummary())

    renderWithProviders(<EvalsScreen />)

    expect(await screen.findByText('Latest run: passes thresholds')).toBeInTheDocument()
    expect(screen.getByText(/commit dead123/)).toBeInTheDocument()
    expect(screen.getByText(/12 minutes ago/)).toBeInTheDocument()
    expect(screen.getByText('quick_coverage')).toBeInTheDocument()
    expect(screen.getByText('no_candidates')).toBeInTheDocument()
    expect(screen.getByText('gpt-4o-mini')).toBeInTheDocument()
    // The old "not live yet" note is gone: the data is real now.
    expect(screen.queryByText(/not live yet/i)).not.toBeInTheDocument()
  })

  it('renders a failing run as failing', async () => {
    vi.mocked(fetchEvalSummary).mockResolvedValue(liveSummary({ passed: false }))

    renderWithProviders(<EvalsScreen />)

    expect(await screen.findByText('Latest run: FAILING')).toBeInTheDocument()
  })

  it('shows the honest empty state naming the exact command when there are no runs', async () => {
    vi.mocked(fetchEvalSummary).mockResolvedValue(
      liveSummary({
        hasRuns: false,
        commit: '',
        ranAgo: '',
        accuracyHistory: [],
        latestAccuracy: 0,
        scenarios: [],
        models: [],
      }),
    )

    renderWithProviders(<EvalsScreen />)

    expect(await screen.findByText('No eval runs recorded yet')).toBeInTheDocument()
    expect(
      screen.getByText(
        'cd backend && uv run python ../evals/runner.py --provider interpreter',
      ),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('evals-grid')).not.toBeInTheDocument()
  })

  it('says so instead of rendering zeros when a section has no data yet', async () => {
    vi.mocked(fetchEvalSummary).mockResolvedValue(
      liveSummary({ accuracyHistory: [], scenarios: [], models: [] }),
    )

    renderWithProviders(<EvalsScreen />)

    expect(await screen.findByTestId('evals-grid')).toBeInTheDocument()
    expect(
      screen.getByText(/No golden-set runs recorded yet/),
    ).toBeInTheDocument()
    expect(screen.getByText(/No scenario run recorded yet/)).toBeInTheDocument()
    expect(screen.getByText(/No model comparison yet/)).toBeInTheDocument()
  })
})

describe('EvalsScreen behind VITE_USE_MOCK', () => {
  beforeEach(() => {
    vi.mocked(fetchEvalSummary).mockReset()
    vi.mocked(isMockMode).mockReturnValue(true)
  })

  it('still renders the mock fixture without touching the API', async () => {
    renderWithProviders(<EvalsScreen />)

    expect(await screen.findByTestId('evals-grid')).toBeInTheDocument()
    expect(screen.getByText('quick_yes')).toBeInTheDocument() // mock scenario id
    expect(fetchEvalSummary).not.toHaveBeenCalled()
    expect(screen.queryByText(/not live yet/i)).not.toBeInTheDocument()
  })
})
