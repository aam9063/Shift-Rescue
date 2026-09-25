import { useState, type FormEvent } from 'react'
import type { SimulatorEmployee } from '../domain/types'
import { useDemoClock, useDemoEmployees, useDemoThread, useSendDemoMessage } from '../services/dashboard'

const CLOCK_PRESETS = [
  { label: '+10 min', seconds: 600 },
  { label: '+1h', seconds: 3600 },
]

function initials(name: string): string {
  return (
    name
      .split(' ')
      .map((part) => part[0])
      .slice(0, 2)
      .join('')
      .toUpperCase() || '?'
  )
}

/**
 * One employee phone (spec §7.6, mockup "Simulador de demo"): the employee's
 * real conversation thread with a "send as this employee" action. In live
 * mode the message travels the same pipeline as a real WhatsApp message.
 */
function EmployeePhone({ employee }: { employee: SimulatorEmployee }) {
  const { messages } = useDemoThread(employee.conversationId)
  const { send } = useSendDemoMessage()
  const [draft, setDraft] = useState('')

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const text = draft.trim()
    if (!text) {
      return
    }
    send(employee.id, employee.conversationId, text)
    setDraft('')
  }

  return (
    <div className="flex h-[480px] flex-col rounded-card border-4 border-green-house bg-neutral-cool">
      <div className="flex items-center gap-3 border-b border-black/10 px-4 py-3">
        <span className="flex size-9 items-center justify-center rounded-full bg-green-accent text-sm font-bold text-white">
          {initials(employee.displayName)}
        </span>
        <div>
          <p className="text-base font-semibold tracking-tight">{employee.displayName}</p>
          <p className="text-xs tracking-tight text-text-secondary">
            {employee.roles.length > 0 ? employee.roles.join(' · ') : 'Demo phone'}
            {employee.shiftStartsAt !== null && employee.shiftEndsAt !== null
              ? ` · ${employee.shiftStartsAt.slice(11, 16)}–${employee.shiftEndsAt.slice(11, 16)}`
              : ''}
            {employee.shiftStatus !== null ? ` (${employee.shiftStatus})` : ''}
          </p>
        </div>
      </div>
      <div className="flex-1 space-y-2 overflow-y-auto p-3" aria-label={`Thread of ${employee.displayName}`}>
        {messages.map((message, index) => (
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
        onSubmit={submit}
      >
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Message"
          aria-label={`Message for ${employee.displayName}`}
          className="min-w-0 flex-1 rounded-pill border border-black/10 bg-white px-3 py-2 text-sm tracking-tight"
        />
        <button
          type="submit"
          aria-label={`Send message to ${employee.displayName}`}
          className="pointer-coarse:size-11 flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-full bg-green-accent text-white transition-transform active:scale-95"
        >
          <svg viewBox="0 0 16 16" className="size-4 fill-white" aria-hidden="true">
            <path d="M1 8 15 1 9.5 15 7.8 9.2 1 8Z" />
          </svg>
        </button>
      </form>
    </div>
  )
}

/**
 * Demo simulator (spec §7.6 screen 6): phone frames of the real employees
 * with WhatsApp-style chats, the shared demo clock, and the honest
 * limitation spelled out — broker timers follow real time, deadlines and
 * escalations follow the demo clock.
 */
export function SimulatorScreen() {
  const { employees } = useDemoEmployees()
  const { time, advance } = useDemoClock()

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
        {employees.slice(0, 3).map((employee) => (
          <EmployeePhone key={employee.id} employee={employee} />
        ))}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-4 rounded-card bg-surface px-4 py-3 shadow-card">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm tracking-tight text-text-secondary">
            Demo clock: <span className="font-semibold text-text-primary">{time ?? '--:--'}</span>
          </span>
          {CLOCK_PRESETS.map((preset) => (
            <button
              key={preset.seconds}
              type="button"
              onClick={() => advance(preset.seconds)}
              className="pointer-coarse:min-h-11 cursor-pointer rounded-pill bg-green-house px-4 py-2 text-sm font-semibold tracking-tight text-white active:scale-95"
            >
              {preset.label}
            </button>
          ))}
          <p className="w-full text-xs tracking-tight text-text-secondary">
            Broker timers keep their real-time ETA; deadlines and escalations follow the demo clock.
          </p>
        </div>
        <button
          type="button"
          className="pointer-coarse:min-h-11 cursor-pointer rounded-pill border border-black/10 bg-surface px-4 py-2 text-sm font-semibold tracking-tight text-text-primary active:scale-95"
        >
          Load scenario: acceptance race
        </button>
      </div>
    </div>
  )
}
