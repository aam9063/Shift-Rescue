import { useState, type FormEvent } from 'react'
import type { SimulatorEmployee } from '../domain/types'
import {
  useAcceptanceRaceScenario,
  useDemoClock,
  useDemoEmployees,
  useDemoThread,
  useSendDemoMessage,
} from '../services/dashboard'

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

// --- Roster situation (demo-readiness T1): who can report an absence now? ----

type EmployeeSituationKind = 'on-shift' | 'starts-later' | 'shift-ended' | 'no-shift'

interface EmployeeSituation {
  kind: EmployeeSituationKind
  /** Human label shown in the frame header, e.g. "Starts at 17:00". */
  label: string
}

/**
 * The employee's situation against the current (virtual) time. Frames that
 * cannot produce a rescue still render, but say why: the agent correctly
 * answers "out of scope" for employees who are not on shift right now.
 * Pure: the moment is always injected for deterministic tests.
 */
function employeeSituation(employee: SimulatorEmployee, now: Date): EmployeeSituation {
  if (employee.shiftStartsAt === null || employee.shiftEndsAt === null) {
    return { kind: 'no-shift', label: 'No shift today' }
  }
  const startsAt = new Date(employee.shiftStartsAt)
  const endsAt = new Date(employee.shiftEndsAt)
  if (now < startsAt) {
    return { kind: 'starts-later', label: `Starts at ${employee.shiftStartsAt.slice(11, 16)}` }
  }
  if (now >= endsAt) {
    return { kind: 'shift-ended', label: `Ended at ${employee.shiftEndsAt.slice(11, 16)}` }
  }
  return { kind: 'on-shift', label: 'On shift now' }
}

/** Actionable employees (on shift now) sort first; the rest stay visible. */
const SITUATION_RANK: Record<EmployeeSituationKind, number> = {
  'on-shift': 0,
  'starts-later': 1,
  'shift-ended': 2,
  'no-shift': 3,
}

const SITUATION_BADGE_CLASSES: Record<EmployeeSituationKind, string> = {
  'on-shift': 'bg-green-accent text-white',
  'starts-later': 'bg-green-light text-green-house',
  'shift-ended': 'bg-black/5 text-text-secondary',
  'no-shift': 'bg-black/5 text-text-secondary',
}

/** Offset in human terms: "+2 h 30 m ahead", "-15 m behind", "on real time". */
function formatDemoOffset(seconds: number): string {
  if (seconds === 0) {
    return 'on real time'
  }
  const sign = seconds > 0 ? '+' : '-'
  const abs = Math.abs(seconds)
  const hours = Math.floor(abs / 3600)
  const minutes = Math.round((abs % 3600) / 60)
  const parts: string[] = []
  if (hours > 0) {
    parts.push(`${hours} h`)
  }
  if (minutes > 0 || hours === 0) {
    parts.push(`${minutes} m`)
  }
  return `${sign}${parts.join(' ')} ${seconds > 0 ? 'ahead' : 'behind'}`
}

/**
 * One employee phone (spec §7.6, mockup "Simulador de demo"): the employee's
 * real conversation thread with a "send as this employee" action. In live
 * mode the message travels the same pipeline as a real WhatsApp message.
 * The header states the employee's situation so it is obvious whether the
 * agent can act for them.
 */
function EmployeePhone({
  employee,
  situation,
}: {
  employee: SimulatorEmployee
  situation: EmployeeSituation
}) {
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
    <div
      data-testid="employee-frame"
      className="flex h-[480px] flex-col rounded-card border-4 border-green-house bg-neutral-cool"
    >
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
          <span
            aria-label={`Situation of ${employee.displayName}`}
            className={`mt-1 inline-flex rounded-pill px-2 py-0.5 text-xs font-semibold tracking-tight ${
              SITUATION_BADGE_CLASSES[situation.kind]
            }`}
          >
            {situation.label}
          </span>
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
 * escalations follow the demo clock. Employees who can report an absence
 * right now come first; when nobody can, the screen says so and what to do.
 */
export function SimulatorScreen() {
  const { employees } = useDemoEmployees()
  const { time, offsetSeconds, virtualNow, advance, reset } = useDemoClock()
  const scenario = useAcceptanceRaceScenario()

  const now = virtualNow ?? new Date()
  const roster = employees
    .map((employee) => ({ employee, situation: employeeSituation(employee, now) }))
    .sort((a, b) => SITUATION_RANK[a.situation.kind] - SITUATION_RANK[b.situation.kind])
  const nobodyOnShift = !roster.some((entry) => entry.situation.kind === 'on-shift')
  const offset = offsetSeconds ?? 0

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

      {nobodyOnShift && (
        <p
          role="status"
          className="rounded-card border border-gold bg-surface px-4 py-3 text-sm tracking-tight text-text-primary shadow-card"
        >
          Nobody is on shift right now, so nobody can report an absence: the agent will answer
          &quot;out of scope&quot;. Reseed the demo data, or reset the demo clock to move
          &quot;now&quot; back to a moment when someone is working.
        </p>
      )}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
        {roster.slice(0, 3).map(({ employee, situation }) => (
          <EmployeePhone key={employee.id} employee={employee} situation={situation} />
        ))}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-4 rounded-card bg-surface px-4 py-3 shadow-card">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm tracking-tight text-text-secondary">
            Demo clock: <span className="font-semibold text-text-primary">{time ?? '--:--'}</span>
            {offsetSeconds !== undefined && (
              <> ({formatDemoOffset(offsetSeconds)})</>
            )}
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
          <button
            type="button"
            onClick={reset}
            className="pointer-coarse:min-h-11 cursor-pointer rounded-pill border border-black/10 bg-surface px-4 py-2 text-sm font-semibold tracking-tight text-text-primary active:scale-95"
          >
            Reset clock
          </button>
          <p className="w-full text-xs tracking-tight text-text-secondary">
            Broker timers keep their real-time ETA; deadlines and escalations follow the demo clock.
            {offset !== 0 &&
              ` The agent's "now" is shifted ${formatDemoOffset(offset)}: conversations and deadlines follow the shifted clock. Reset it if the screens look displaced.`}
          </p>
        </div>
        <div className="flex flex-col items-start gap-1">
          <button
            type="button"
            onClick={scenario.run}
            disabled={scenario.status !== 'ready'}
            className="pointer-coarse:min-h-11 cursor-pointer rounded-pill border border-black/10 bg-surface px-4 py-2 text-sm font-semibold tracking-tight text-text-primary active:scale-95 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {scenario.status === 'running'
              ? 'Running scenario…'
              : 'Run scenario: two candidates accept at once'}
          </button>
          {scenario.message !== '' && (
            <p className="text-xs tracking-tight text-text-secondary">{scenario.message}</p>
          )}
        </div>
      </div>
    </div>
  )
}
