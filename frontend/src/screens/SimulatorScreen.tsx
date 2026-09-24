import { useState } from 'react'
import { useConversations } from '../services/dashboard'

const DEMO_CLOCK_START = '15:11'

/**
 * Demo simulator (spec §7.6 screen 6, mockup "Simulador de demo"): phone
 * frames of the fictional employees with WhatsApp-style chats, a simulated
 * clock and predefined scenarios.
 */
export function SimulatorScreen() {
  const { conversations } = useConversations()
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [threads, setThreads] = useState<Record<string, { from: 'employee' | 'assistant'; text: string }[]>>(
    () => Object.fromEntries(conversations.map((c) => [c.employeeId, [...c.messages]])),
  )
  const [clock, setClock] = useState(DEMO_CLOCK_START)

  const send = (employeeId: string) => {
    const text = (drafts[employeeId] ?? '').trim()
    if (!text) {
      return
    }
    setThreads((current) => ({
      ...current,
      [employeeId]: [...(current[employeeId] ?? []), { from: 'employee', text }],
    }))
    setDrafts((current) => ({ ...current, [employeeId]: '' }))
  }

  const advance = (minutes: number) => {
    const [h, m] = clock.split(':').map(Number)
    const total = h * 60 + m + minutes
    setClock(`${String(Math.floor(total / 60) % 24).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`)
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-baseline gap-3">
        <h1 className="font-serif text-4xl font-semibold tracking-tight text-green-starbucks">
          Employee phones
        </h1>
        <p className="text-sm text-text-secondary">
          Write as any of them to test the agent
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
        {conversations.slice(0, 3).map((conversation) => (
          <div
            key={conversation.employeeId}
            className="flex h-[480px] flex-col rounded-card border-4 border-green-house bg-neutral-cool"
          >
            <div className="flex items-center gap-3 border-b border-black/10 px-4 py-3">
              <span className="flex size-9 items-center justify-center rounded-full bg-green-accent text-sm font-bold text-white">
                {conversation.initials}
              </span>
              <p className="text-base font-semibold tracking-tight">{conversation.employeeName}</p>
            </div>
            <div className="flex-1 space-y-2 overflow-y-auto p-3">
              {(threads[conversation.employeeId] ?? []).map((message, index) => (
                <div
                  key={index}
                  className={`max-w-[90%] rounded-card px-3 py-2 text-sm tracking-tight ${
                    message.from === 'assistant'
                      ? 'ml-auto bg-green-light text-green-house'
                      : 'bg-white text-text-primary'
                  }`}
                >
                  {message.text}
                </div>
              ))}
            </div>
            <form
              className="flex items-center gap-2 border-t border-black/10 p-3"
              onSubmit={(event) => {
                event.preventDefault()
                send(conversation.employeeId)
              }}
            >
              <input
                value={drafts[conversation.employeeId] ?? ''}
                onChange={(event) =>
                  setDrafts((current) => ({ ...current, [conversation.employeeId]: event.target.value }))
                }
                placeholder="Message"
                aria-label={`Mensaje para ${conversation.employeeName}`}
                className="min-w-0 flex-1 rounded-pill border border-black/10 bg-white px-3 py-2 text-sm tracking-tight"
              />
              <button
                type="submit"
                aria-label={`Enviar mensaje a ${conversation.employeeName}`}
                className="flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-full bg-green-accent text-white transition-transform active:scale-95"
              >
                <svg viewBox="0 0 16 16" className="size-4 fill-white" aria-hidden="true">
                  <path d="M1 8 15 1 9.5 15 7.8 9.2 1 8Z" />
                </svg>
              </button>
            </form>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-4 rounded-card bg-surface px-4 py-3 shadow-card">
        <div className="flex items-center gap-3">
          <span className="text-sm tracking-tight text-text-secondary">
            Simulated clock: <span className="font-semibold text-text-primary">{clock}</span>
          </span>
          <button
            type="button"
            onClick={() => advance(10)}
            className="cursor-pointer rounded-pill bg-green-house px-4 py-2 text-sm font-semibold tracking-tight text-white active:scale-95"
          >
            +10 min
          </button>
          <button
            type="button"
            onClick={() => advance(60)}
            className="cursor-pointer rounded-pill bg-green-house px-4 py-2 text-sm font-semibold tracking-tight text-white active:scale-95"
          >
            +1h
          </button>
        </div>
        <button
          type="button"
          className="cursor-pointer rounded-pill border border-black/10 bg-surface px-4 py-2 text-sm font-semibold tracking-tight text-text-primary active:scale-95"
        >
          Load scenario: acceptance race
        </button>
      </div>
    </div>
  )
}
