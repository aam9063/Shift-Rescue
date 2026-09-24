import {
  eventLabel,
  orderCandidates,
  sortEventsChronologically,
} from '../domain/rescue'
import type { AuditEvent, CandidateResult, Offer, OfferStatus, RescueDetail } from '../domain/types'
import { formatCountdown, formatShiftTime } from '../domain/today'
import { useRescueDetail } from '../services/hooks'

const TIMEZONE = 'Europe/Madrid'

const rescueStatusLabels: Record<string, string> = {
  OPEN: 'Opening rescue',
  OFFERING: 'Searching',
  AWAITING_APPROVAL: 'Needs your approval',
  COVERED: 'Covered',
  ESCALATED: 'Escalated to manager',
}

/** Timeline dot color by event semantics (mockup: gray system, green offers, red rejections). */
const eventDotClasses: Partial<Record<AuditEvent['type'], string>> = {
  OFFER_SENT: 'bg-green-accent',
  OFFER_ACCEPTED: 'bg-green-accent',
  OFFER_DECLINED: 'bg-error',
  ESCALATED: 'bg-error',
}

function offerStatusFor(candidate: CandidateResult, offers: Offer[]): OfferStatus | undefined {
  return offers.find((o) => o.employeeName === candidate.name)?.status
}

const offerStatusLabel: Record<OfferStatus, string> = {
  PENDING: 'pending',
  ACCEPTED: 'accepted',
  DECLINED: 'declined',
  COUNTER_PROPOSED: 'counter-proposed',
  EXPIRED: 'expired',
  CANCELLED: 'cancelled',
  SUPERSEDED: 'superseded',
  WITHDRAWN: 'withdrawn',
}

const offerStatusClasses: Partial<Record<OfferStatus, string>> = {
  DECLINED: 'text-error',
  WITHDRAWN: 'text-error',
  ACCEPTED: 'text-green-accent',
}

function timeOf(iso: string): string {
  return new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: TIMEZONE,
  }).format(new Date(iso))
}

function Hero({ detail, now, onBack }: { detail: RescueDetail; now: Date; onBack: () => void }) {
  const countdown = formatCountdown(detail.rescue.deadlineAt, now)
  const wave =
    detail.rescue.waveCurrent != null && detail.rescue.waveTotal != null
      ? ` · wave ${detail.rescue.waveCurrent} of ${detail.rescue.waveTotal}`
      : ''
  return (
    <div className="bg-green-house px-4 py-8 text-white md:px-10">
      <div className="mx-auto max-w-[1200px]">
        <button
          type="button"
          onClick={onBack}
          className="cursor-pointer text-sm font-medium tracking-tight text-white/80 transition-colors hover:text-white"
        >
          ‹ Back to Today
        </button>
        <div className="mt-2 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-serif text-4xl font-semibold tracking-tight md:text-5xl">
              {detail.shift.role.charAt(0).toUpperCase() + detail.shift.role.slice(1)} ·{' '}
              {formatShiftTime(detail.shift, TIMEZONE)}
            </h1>
            <p className="mt-2 text-base tracking-tight text-white/70">
              Absent: {detail.rescue.absentEmployeeName}
              {detail.rescue.openedAt ? ` · opened at ${timeOf(detail.rescue.openedAt)}` : ''}
            </p>
            <span className="mt-3 inline-block rounded-pill bg-white/15 px-4 py-1.5 text-sm font-semibold tracking-tight">
              {rescueStatusLabels[detail.rescue.status]}
              {wave}
            </span>
          </div>
          <div className="text-right">
            <p className="font-serif text-5xl font-bold tracking-tight md:text-6xl">{countdown}</p>
            <p className="mt-1 text-sm tracking-tight text-white/70">minutes left</p>
          </div>
        </div>
      </div>
    </div>
  )
}

function Timeline({ events }: { events: AuditEvent[] }) {
  return (
    <section aria-label="Rescue progress">
      <h2 className="mb-4 text-xl font-semibold tracking-tight">What the agent did</h2>
      <ol aria-label="Agent timeline" className="space-y-5 border-l border-black/10 pl-5">
        {events.map((event) => (
          <li key={event.id} className="relative">
            <span
              className={`absolute -left-[26px] top-1.5 size-3 rounded-full ${
                eventDotClasses[event.type] ?? 'bg-black/30'
              }`}
            />
            <p className="text-sm font-semibold tracking-tight text-text-secondary">
              {timeOf(event.createdAt)}
              {event.interpretedByAi && (
                <span className="ml-2 inline-block rounded-full bg-green-light px-2 py-0.5 text-xs font-bold text-green-house">
                  AI
                </span>
              )}
            </p>
            <p className="mt-0.5 text-base tracking-tight text-text-primary">
              {eventLabel(event.type)}
              {event.type === 'OFFER_SENT' ? '.' : ''}
            </p>
          </li>
        ))}
      </ol>
    </section>
  )
}

function Candidates({
  candidates,
  offers,
}: {
  candidates: CandidateResult[]
  offers: Offer[]
}) {
  const eligible = orderCandidates(candidates.filter((c) => c.eligible))
  const excluded = candidates.filter((c) => !c.eligible)
  return (
    <section aria-label="Candidates">
      <h2 className="mb-4 text-xl font-semibold tracking-tight">Candidates</h2>
      <ul className="space-y-3">
        {eligible.map((candidate) => {
          const status = offerStatusFor(candidate, offers)
          return (
            <li key={candidate.employeeId} className="rounded-card bg-surface px-4 py-3 shadow-card">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-base font-semibold tracking-tight">{candidate.name}</p>
                  <p className="text-sm tracking-tight text-text-secondary">
                    Score {candidate.score.toFixed(2)} ·{' '}
                    {candidate.requiresApproval ? 'needs approval' : 'no overtime'}
                  </p>
                </div>
                {status && (
                  <span
                    className={`text-sm font-medium tracking-tight ${
                      offerStatusClasses[status] ?? 'text-text-secondary'
                    }`}
                  >
                    {offerStatusLabel[status]}
                  </span>
                )}
              </div>
            </li>
          )
        })}
      </ul>
      {excluded.length > 0 && (
        <>
          <h3 className="mb-2 mt-6 text-base font-semibold tracking-tight">Excluded</h3>
          <ul className="space-y-2">
            {excluded.map((candidate) => (
              <li
                key={candidate.employeeId}
                className="flex items-center justify-between text-sm tracking-tight"
              >
                <span className="text-text-secondary">{candidate.name}</span>
                <span className="font-mono text-xs text-text-secondary">
                  {candidate.reasons.map((r) => r.code).join(', ')}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}

export interface RescueDetailScreenProps {
  rescueId: string
  /** Injected clock for deterministic tests; defaults to now. */
  now?: Date
  /** Called when the user navigates back to the Today screen. */
  onBack: () => void
}

export function RescueDetailScreen({ rescueId, now = new Date(), onBack }: RescueDetailScreenProps) {
  const { detail, isLoading } = useRescueDetail(rescueId)

  if (isLoading || !detail) {
    return <p className="text-base text-text-secondary">Loading…</p>
  }

  return (
    <div>
      <Hero detail={detail} now={now} onBack={onBack} />
      <div className="mx-auto grid max-w-[1200px] grid-cols-1 gap-10 px-4 py-8 md:grid-cols-2 md:px-10">
        <Timeline events={sortEventsChronologically(detail.timeline)} />
        <Candidates candidates={detail.candidates} offers={detail.offers} />
      </div>
    </div>
  )
}
