import { Button } from '../components/ui/Button'
import { eventLabel, orderCandidates, sortEventsChronologically } from '../domain/rescue'
import { rescueCountdown } from '../domain/today'
import type { Offer, OfferStatus } from '../domain/types'
import { formatShiftTime } from '../domain/today'
import { useRescueDetail } from '../services/hooks'

const TIMEZONE = 'Europe/Madrid'

const rescueStatusLabels: Record<string, string> = {
  OPEN: 'Opening rescue',
  OFFERING: 'Offering shift to candidates',
  AWAITING_APPROVAL: 'Waiting for manager approval',
  COVERED: 'Covered',
  ESCALATED: 'Escalated to manager',
}

const offerStatusLabels: Record<OfferStatus, string> = {
  PENDING: 'Pending',
  ACCEPTED: 'Accepted',
  DECLINED: 'Declined',
  COUNTER_PROPOSED: 'Counter-proposed',
  EXPIRED: 'Expired',
  CANCELLED: 'Cancelled',
  SUPERSEDED: 'Superseded',
  WITHDRAWN: 'Withdrawn',
}

const offerBadgeClasses: Record<OfferStatus, string> = {
  PENDING: 'bg-warning/10 border border-warning',
  ACCEPTED: 'bg-green-light border border-green-light',
  DECLINED: 'bg-error/5 border border-error',
  COUNTER_PROPOSED: 'bg-warning/10 border border-warning',
  EXPIRED: 'bg-neutral-cool border border-black/10',
  CANCELLED: 'bg-neutral-cool border border-black/10',
  SUPERSEDED: 'bg-neutral-cool border border-black/10',
  WITHDRAWN: 'bg-error/5 border border-error',
}

function timeOf(iso: string): string {
  return new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: TIMEZONE,
  }).format(new Date(iso))
}

function Timeline({ events }: { events: ReturnType<typeof sortEventsChronologically> }) {
  return (
    <section>
      <h2 className="mb-2 text-xl font-medium tracking-tight">Timeline</h2>
      <ol aria-label="Rescue timeline" className="space-y-2">
        {events.map((event) => (
          <li
            key={event.id}
            className="flex items-baseline justify-between rounded-card bg-surface px-4 py-3 shadow-card"
          >
            <div>
              <p className="text-base font-medium tracking-tight">{eventLabel(event.type)}</p>
              <p className="text-sm tracking-tight text-text-secondary">{event.actor}</p>
            </div>
            <time className="text-sm tracking-tight text-text-secondary">
              {timeOf(event.createdAt)}
            </time>
          </li>
        ))}
      </ol>
    </section>
  )
}

function CandidatesTable({ candidates }: { candidates: ReturnType<typeof orderCandidates> }) {
  return (
    <section aria-label="Candidates">
      <h2 className="mb-2 text-xl font-medium tracking-tight">Candidates</h2>
      <ul className="space-y-2">
        {candidates.map((candidate) => (
          <li key={candidate.employeeId} className="rounded-card bg-surface px-4 py-3 shadow-card">
            <div className="flex items-center justify-between">
              <p className="text-base font-medium tracking-tight">{candidate.name}</p>
              <p className="text-sm font-semibold tracking-tight text-green-starbucks">
                Score {candidate.score.toFixed(2)}
              </p>
            </div>
            {!candidate.eligible ? (
              candidate.reasons.map((reason) => (
                <p key={reason.code} className="text-sm tracking-tight text-error">
                  Not eligible — {reason.message} ({reason.code})
                </p>
              ))
            ) : candidate.requiresApproval ? (
              <>
                {candidate.reasons.map((reason) => (
                  <p key={reason.code} className="text-sm tracking-tight text-text-secondary">
                    Approval needed — {reason.message} ({reason.code})
                  </p>
                ))}
                <p className="text-sm tracking-tight text-text-secondary">
                  Eligible with manager approval
                </p>
              </>
            ) : (
              <p className="text-sm tracking-tight text-text-secondary">Eligible</p>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

function OffersList({ offers }: { offers: Offer[] }) {
  return (
    <section aria-label="Offers">
      <h2 className="mb-2 text-xl font-medium tracking-tight">Offers</h2>
      <ul className="space-y-2">
        {offers.map((offer) => (
          <li key={offer.id} className="flex items-center justify-between rounded-card bg-surface px-4 py-3 shadow-card">
            <div>
              <p className="text-base font-medium tracking-tight">{offer.employeeName}</p>
              <p className="text-sm tracking-tight text-text-secondary">Wave {offer.waveNumber}</p>
            </div>
            <span
              className={`rounded-pill px-3 py-1 text-sm font-medium tracking-tight ${offerBadgeClasses[offer.status]}`}
            >
              {offerStatusLabels[offer.status]}
            </span>
          </li>
        ))}
      </ul>
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
    <div className="space-y-6">
      <Button variant="secondary" onClick={onBack}>
        ← Back to Today
      </Button>
      <header className="rounded-card bg-surface p-6 shadow-card">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-semibold leading-9 tracking-tight text-green-starbucks">
              Rescue — {detail.rescue.absentEmployeeName}
            </h1>
            <p className="mt-1 text-base tracking-tight text-text-secondary">
              {formatShiftTime(detail.shift, TIMEZONE)} ·{" "}
              {rescueStatusLabels[detail.rescue.status]}
            </p>
          </div>
          <p
            className={`text-lg font-semibold tracking-tight ${
              rescueCountdown(detail.rescue, now).urgent ? 'text-error' : 'text-green-starbucks'
            }`}
          >
            {rescueCountdown(detail.rescue, now).label}
          </p>
        </div>
      </header>
      <Timeline events={sortEventsChronologically(detail.timeline)} />
      <CandidatesTable candidates={orderCandidates(detail.candidates)} />
      <OffersList offers={detail.offers} />
    </div>
  )
}
