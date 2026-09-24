import type { RescueCase } from '../domain/types'
import { rescueCountdown } from '../domain/today'

const statusLabels: Record<RescueCase['status'], string> = {
  OPEN: 'Opening rescue',
  OFFERING: 'Offering shift to candidates',
  AWAITING_APPROVAL: 'Waiting for manager approval',
  COVERED: 'Covered',
  ESCALATED: 'Escalated to manager',
}

export interface ActiveRescueBannerProps {
  rescue: RescueCase
  /** Injected clock for deterministic tests; defaults to now. */
  now?: Date
}

/**
 * Highlighted active-rescue card on the dark House Green band (DESIGN.md
 * feature-band treatment). Announced as an alert region for accessibility.
 */
export function ActiveRescueBanner({ rescue, now = new Date() }: ActiveRescueBannerProps) {
  const countdown = rescueCountdown(rescue, now)
  return (
    <div
      role="alert"
      className="flex items-center justify-between rounded-card bg-green-house px-4 py-4 text-white shadow-card md:px-6"
    >
      <div>
        <p className="text-base font-semibold tracking-tight">
          {rescue.absentEmployeeName} can&apos;t make their shift
        </p>
        <p className="text-sm tracking-tight text-text-on-dark-soft">
          {statusLabels[rescue.status]}
        </p>
      </div>
      <p
        className={`text-lg font-semibold tracking-tight ${countdown.urgent ? 'text-warning' : 'text-white'}`}
      >
        {countdown.label}
      </p>
    </div>
  )
}
