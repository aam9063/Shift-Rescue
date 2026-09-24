import type { ReactNode } from 'react'
import { ActiveRescueBanner } from '../components/ActiveRescueBanner'
import { formatShiftTime, groupShiftsByRole } from '../domain/today'
import { RoleOrder, type Shift, type ShiftRole, type ShiftStatus } from '../domain/types'
import { useActiveRescues, useTodayShifts } from '../services/hooks'

const TIMEZONE = 'Europe/Madrid'

const roleLabels: Record<ShiftRole, string> = {
  kitchen: 'Kitchen',
  floor: 'Floor',
  bar: 'Bar',
  cleaning: 'Cleaning',
  supervisor: 'Supervisor',
}

const statusLabels: Record<ShiftStatus, string> = {
  scheduled: 'Scheduled',
  covered: 'Covered',
  open: 'Open',
  absent: 'Absent',
}

/** Badge colors follow DESIGN.md semantic colors on pill surfaces. */
const statusBadgeClasses: Record<ShiftStatus, string> = {
  scheduled: 'bg-neutral-cool text-text-secondary border border-black/10',
  covered: 'bg-green-light text-green-house border border-green-light',
  open: 'bg-warning/10 text-text-primary border border-warning',
  absent: 'bg-error/5 text-error border border-error',
}

function StatusBadge({ status }: { status: ShiftStatus }) {
  return (
    <span
      className={`rounded-pill px-3 py-1 text-sm font-medium tracking-tight ${statusBadgeClasses[status]}`}
    >
      {statusLabels[status]}
    </span>
  )
}

function ShiftCard({ shift }: { shift: Shift }) {
  return (
    <div className="flex items-center justify-between rounded-card bg-surface px-4 py-3 shadow-card">
      <div>
        <p className="text-base font-semibold tracking-tight">
          {formatShiftTime(shift, TIMEZONE)}
        </p>
        <p className="text-sm tracking-tight text-text-secondary">
          {shift.assigneeName ?? 'Unassigned'}
        </p>
      </div>
      <StatusBadge status={shift.status} />
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="space-y-2">
      <h2 className="text-xl font-medium tracking-tight text-text-primary">{title}</h2>
      {children}
    </section>
  )
}

export interface TodayScreenProps {
  /** Injected clock for deterministic tests; defaults to now. */
  now?: Date
  /** Called with the rescue id when the user opens a rescue from its banner. */
  onOpenRescue?: (rescueId: string) => void
}

export function TodayScreen({ now = new Date(), onOpenRescue }: TodayScreenProps) {
  const dayIso = now.toISOString().slice(0, 10)
  const { shifts, isLoading } = useTodayShifts(dayIso)
  const { rescues } = useActiveRescues()

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold leading-9 tracking-tight text-green-starbucks">
        Today
      </h1>
      {rescues && rescues.length > 0 && (
        <div>
          {rescues.map((rescue) => (
            <button
              key={rescue.id}
              type="button"
              onClick={() => onOpenRescue?.(rescue.id)}
              className="mb-6 block w-full cursor-pointer rounded-card text-left transition-opacity hover:opacity-90"
            >
              <ActiveRescueBanner rescue={rescue} now={now} />
            </button>
          ))}
        </div>
      )}
      {isLoading ? (
        <p className="text-base text-text-secondary">Loading…</p>
      ) : !shifts || shifts.length === 0 ? (
        <p className="text-base text-text-secondary">No shifts scheduled for today</p>
      ) : (
        <>
          {groupShiftsByRole(shifts, RoleOrder).map((group) => (
            <Section key={group.role} title={roleLabels[group.role]}>
              {group.shifts.map((shift) => (
                <ShiftCard key={shift.id} shift={shift} />
              ))}
            </Section>
          ))}
        </>
      )}
    </div>
  )
}
