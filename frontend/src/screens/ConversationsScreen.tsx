import { useState } from 'react'
import { useConversations } from '../services/dashboard'

const INTENT_CLASSES: Record<string, string> = {
  OFFER_CONDITIONAL: 'text-gold',
  ABSENCE_REPORT: 'text-green-starbucks',
  UNCLEAR: 'text-error',
}

function IntentLabel({ intent }: { intent: string }) {
  return (
    <span className={`text-xs font-semibold uppercase tracking-wide ${INTENT_CLASSES[intent] ?? 'text-text-secondary'}`}>
      {intent}
    </span>
  )
}

/**
 * Conversations screen (spec §7.6 screen 7, mockup "Conversations"): every
 * conversation with its interpreted intent plus a WhatsApp-style chat panel
 * with redacted bodies.
 */
export function ConversationsScreen() {
  const { conversations } = useConversations()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const selected = conversations.find((c) => c.employeeId === selectedId) ?? null

  return (
    <div className="space-y-6">
      <h1 className="font-serif text-4xl font-semibold tracking-tight text-green-starbucks">
        Conversations
      </h1>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <ul aria-label="Conversations" className="space-y-3 md:hidden">
          {conversations.map((conversation) => (
            <li key={conversation.employeeId}>
              <button
                type="button"
                onClick={() => setSelectedId(conversation.employeeId)}
                className={`w-full cursor-pointer rounded-card bg-surface px-4 py-3 text-left shadow-card transition-colors hover:bg-neutral-cool focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-accent ${
                  selectedId === conversation.employeeId ? 'bg-green-light/40' : ''
                }`}
              >
                <div className="flex items-baseline justify-between gap-3">
                  <p className="text-sm font-semibold tracking-tight">
                    {conversation.employeeName}
                  </p>
                  <IntentLabel intent={conversation.intent} />
                </div>
                <p className="mt-1 text-sm tracking-tight text-text-secondary">
                  {conversation.lastMessage}
                </p>
                <p className="mt-1 text-sm text-text-secondary">{conversation.rescueLabel}</p>
              </button>
            </li>
          ))}
        </ul>

        <div
          data-testid="conversations-table"
          className="hidden overflow-x-auto rounded-card bg-surface px-4 py-2 shadow-card md:block lg:col-span-2"
        >
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-black/5 text-xs uppercase tracking-wider text-text-secondary">
                <th className="py-3 pr-4 font-medium">Employee</th>
                <th className="py-3 pr-4 font-medium">Last message</th>
                <th className="py-3 pr-4 font-medium">Intent</th>
                <th className="py-3 font-medium">Rescue</th>
              </tr>
            </thead>
            <tbody>
              {conversations.map((conversation) => (
                <tr
                  key={conversation.employeeId}
                  onClick={() => setSelectedId(conversation.employeeId)}
                  className={`cursor-pointer border-b border-black/5 transition-colors last:border-0 hover:bg-neutral-cool ${
                    selectedId === conversation.employeeId ? 'bg-green-light/40' : ''
                  }`}
                >
                  <td className="py-3 pr-4 text-sm font-semibold tracking-tight">
                    {conversation.employeeName}
                  </td>
                  <td className="py-3 pr-4 text-sm text-text-secondary">
                    {conversation.lastMessage}
                  </td>
                  <td className="py-3 pr-4">
                    <IntentLabel intent={conversation.intent} />
                  </td>
                  <td className="py-3 text-sm text-text-secondary">{conversation.rescueLabel}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {selected ? (
          <aside
            aria-label="Chat"
            className="flex max-h-[560px] flex-col rounded-card bg-surface shadow-card"
          >
            <div className="flex items-center gap-3 border-b border-black/5 px-4 py-3">
              <span className="flex size-9 items-center justify-center rounded-full bg-green-accent text-sm font-bold text-white">
                {selected.initials}
              </span>
              <p className="text-base font-semibold tracking-tight">{selected.employeeName}</p>
            </div>
            <div className="flex-1 space-y-2 overflow-y-auto p-4">
              {selected.messages.map((message, index) => (
                <div
                  key={index}
                  className={`max-w-[85%] rounded-card px-3 py-2 text-sm tracking-tight ${
                    message.from === 'assistant'
                      ? 'ml-auto bg-green-light text-green-house'
                      : 'bg-neutral-cool text-text-primary'
                  }`}
                >
                  {message.text}
                </div>
              ))}
            </div>
          </aside>
        ) : (
          <aside
            aria-label="Chat"
            className="hidden place-items-center rounded-card bg-surface text-sm text-text-secondary shadow-card lg:grid"
          >
            Select a conversation
          </aside>
        )}
      </div>
    </div>
  )
}
