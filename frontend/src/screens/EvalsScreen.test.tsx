import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderWithProviders } from '../test/renderWithProviders'
import { EvalsScreen } from './EvalsScreen'

/**
 * Responsive contract (DESIGN.md §8 gutter/column scale). jsdom evaluates no
 * media queries, so this test pins the CSS-class contract of the grid; the
 * parent verifies the visual result at 768px (tablet) and 1440px.
 */
describe('EvalsScreen responsive contract', () => {
  it('steps the results grid 1 -> 2 -> 5 columns across breakpoints', async () => {
    renderWithProviders(<EvalsScreen />)

    const grid = await screen.findByTestId('evals-grid')
    expect(grid).toHaveClass('grid-cols-1', 'md:grid-cols-2', 'lg:grid-cols-5')
  })
})
