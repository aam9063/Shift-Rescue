import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderWithProviders } from '../test/renderWithProviders'
import { AGENT_DECISIONS } from '../services/dashboardMock'
import { AgentDecisionsScreen } from './AgentDecisionsScreen'

/**
 * Responsive contract (DESIGN.md §8: wide data becomes a list on small
 * screens). jsdom evaluates no media queries, so these tests pin the CSS-class
 * contract — the card list below `md` and the table from `md` up are
 * CSS-controlled siblings, both rendered with the same row data. The parent
 * verifies the visual result at 360px.
 */
describe('AgentDecisionsScreen responsive contract', () => {
  it('renders the card list (md:hidden) and the table (hidden md:block) as siblings', async () => {
    renderWithProviders(<AgentDecisionsScreen />)

    const cardList = await screen.findByRole('list', { name: 'Agent decisions' })
    expect(cardList).toHaveClass('md:hidden')

    const tableWrap = screen.getByTestId('agent-decisions-table')
    expect(tableWrap).toHaveClass('hidden', 'md:block', 'overflow-x-auto')
  })

  it('renders identical row data in both variants', async () => {
    renderWithProviders(<AgentDecisionsScreen />)

    const cardList = await screen.findByRole('list', { name: 'Agent decisions' })
    const cards = await within(cardList).findAllByRole('listitem')
    const rows = (await within(screen.getByRole('table')).findAllByRole('row')).slice(1)

    expect(cards).toHaveLength(AGENT_DECISIONS.length)
    expect(rows).toHaveLength(AGENT_DECISIONS.length)
    AGENT_DECISIONS.forEach((decision, index) => {
      expect(cards[index].textContent).toContain(decision.employeeName)
      expect(cards[index].textContent).toContain(decision.intent)
      expect(cards[index].textContent).toContain(decision.model)
      expect(cards[index].textContent).toContain(decision.validation)
      expect(rows[index].textContent).toContain(decision.employeeName)
      expect(rows[index].textContent).toContain(decision.intent)
      expect(rows[index].textContent).toContain(decision.model)
      expect(rows[index].textContent).toContain(decision.validation)
    })
  })

  it('gives the filter pills the touch-target class for touch surfaces', async () => {
    renderWithProviders(<AgentDecisionsScreen />)

    const filter = await screen.findByRole('button', { name: 'Low confidence' })
    expect(filter).toHaveClass('pointer-coarse:min-h-11')
  })
})
