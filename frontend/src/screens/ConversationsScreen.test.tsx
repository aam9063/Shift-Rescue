import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { renderWithProviders } from '../test/renderWithProviders'
import { CONVERSATIONS } from '../services/dashboardMock'
import { ConversationsScreen } from './ConversationsScreen'

/**
 * Responsive contract (DESIGN.md §8: wide data becomes a list on small
 * screens). jsdom evaluates no media queries, so these tests pin the
 * CSS-class contract — the card list below `md` and the message table from
 * `md` up are CSS-controlled siblings, both rendered with the same row data.
 * The parent verifies the visual result at 360px.
 */
describe('ConversationsScreen responsive contract', () => {
  it('renders the card list (md:hidden) and the table (hidden md:block) as siblings', async () => {
    renderWithProviders(<ConversationsScreen />)

    const cardList = await screen.findByRole('list', { name: 'Conversations' })
    expect(cardList).toHaveClass('md:hidden')

    const tableWrap = screen.getByTestId('conversations-table')
    expect(tableWrap).toHaveClass('hidden', 'md:block', 'overflow-x-auto')
  })

  it('renders identical row data in both variants', async () => {
    renderWithProviders(<ConversationsScreen />)

    const cardList = await screen.findByRole('list', { name: 'Conversations' })
    const cards = await within(cardList).findAllByRole('listitem')
    const rows = (await within(screen.getByRole('table')).findAllByRole('row')).slice(1)

    expect(cards).toHaveLength(CONVERSATIONS.length)
    expect(rows).toHaveLength(CONVERSATIONS.length)
    CONVERSATIONS.forEach((conversation, index) => {
      expect(cards[index].textContent).toContain(conversation.employeeName)
      expect(cards[index].textContent).toContain(conversation.lastMessage)
      expect(cards[index].textContent).toContain(conversation.rescueLabel)
      expect(rows[index].textContent).toContain(conversation.employeeName)
      expect(rows[index].textContent).toContain(conversation.lastMessage)
      expect(rows[index].textContent).toContain(conversation.rescueLabel)
    })
  })

  it('selects a conversation from the card list to open the chat panel', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ConversationsScreen />)

    const cardList = await screen.findByRole('list', { name: 'Conversations' })
    const cards = await within(cardList).findAllByRole('button')
    await user.click(cards[0])

    const chat = await screen.findByRole('complementary', { name: 'Chat' })
    expect(chat).toHaveTextContent(CONVERSATIONS[0].employeeName)
  })
})
