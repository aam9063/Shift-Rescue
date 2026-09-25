import { buildTodayRows, formatCountdownParts, formatShiftTime, type TodayRow } from '../domain/today'
import {
  type Shift,
  type ShiftRole,
  RoleOrder,
  type ShiftStatus,
} from '../domain/types'
import { approvalKindLabel } from '../domain/approvals'
import { useActiveRescues, usePendingApprovals, useTodayShifts } from '../services/hooks'

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
  absent: 'Absent',
  open: 'Open',
  covered: 'Covered',
}

/** Badge per row state: the old board columns, rendered as a badge. */
const stateBadge: Record<TodayRow['state'], { label: string; className: string }> = {
  uncovered: { label: 'Uncovered', className: 'bg-error/10 text-error' },
  searching: { label: 'Searching', className: 'bg-green-accent text-white' },
  'awaiting-approval': { label: 'Needs approval', className: 'bg-gold text-green-house' },
  escalated: { label: 'Escalated', className: 'bg-error text-white' },
  covered: { label: 'Covered', className: 'bg-green-light text-green-house' },
}

/** Honest caption per terminal row state: what happened, no spin. */
const stateCaption: Partial<Record<TodayRow['state'], string>> = {
  uncovered: 'No candidates offered yet.',
  escalated: 'The manager was notified — nobody covered it in time.',
}

function formatLongDate(now: Date): string {
  return new Intl.DateTimeFormat('en-GB', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    timeZone: TIMEZONE,
  }).format(now)
}

function isUrgent(deadlineAt: string, now: Date): boolean {
  return new Date(deadlineAt).getTime() - now.getTime() <= 5 * 60_000
}

/** The countdown that matters for this row: the approval window when one is
 * pending, otherwise the rescue deadline. */
function rowDeadline(row: TodayRow): string {
  const approval = row.approvals.find((a) => a.expiresAt !== undefined)
  if (approval?.expiresAt !== undefined) {
    return approval.expiresAt
  }
  return row.rescue!.deadlineAt
}

function RescueBadge({ state }: { state: TodayRow['state'] }) {
  const badge = stateBadge[state]
  return (
    <span
      className={`inline-flex items-center rounded-pill px-3 py-1 text-xs font-semibold tracking-tight ${badge.className}`}
    >
      {badge.label}
    </span>
  )
}

function Countdown({ deadline, now }: { deadline: string; now: Date }) {
  const parts = formatCountdownParts(deadline, now)
  return (
    <p
      className={`text-xl font-bold tracking-tight ${
        isUrgent(deadline, now) ? 'text-error' : 'text-text-primary'
      }`}
    >
      {parts.text}
      <span className="ml-1 text-xs font-normal text-text-secondary">{parts.caption}</span>
    </p>
  )
}

/** Rescue cell: badge, compact countdown and the extra context the old
 * seeking/approval cards carried (wave, absent employee, approval kind). */
function RescueCell({
  row,
  now,
  onOpenRescue,
  onOpenApprovals,
}: {
  row: TodayRow
  now: Date
  onOpenRescue?: (rescueId: string) => void
  onOpenApprovals?: () => void
}) {
  if (row.state === 'covered') {
    return <span className="text-sm text-text-secondary">—</span>
  }
  return (
    <div className="space-y-1">
      <RescueBadge state={row.state} />
      {row.state === 'uncovered' || row.state === 'escalated' ? (
        <p className="text-xs tracking-tight text-text-secondary">{stateCaption[row.state]}</p>
      ) : (
        <>
          {/* The countdown opens the rescue detail, like the old seeking card. */}
          <button
            type="button"
            onClick={() => onOpenRescue?.(row.rescue!.id)}
            aria-label={`Open rescue detail for ${roleLabels[row.shift.role]}`}
            className="block cursor-pointer text-left"
          >
            <Countdown deadline={rowDeadline(row)} now={now} />
          </button>
          {row.rescue?.waveCurrent != null && row.rescue?.waveTotal != null && (
            <p className="text-xs tracking-tight text-text-secondary">
              wave {row.rescue.waveCurrent} of {row.rescue.waveTotal}
            </p>
          )}
          {row.approvals.map((approval) => (
            <p key={approval.id} className="text-xs tracking-tight text-text-secondary">
              {approvalKindLabel(approval.kind)}
              {approval.context.detail ? ` — ${approval.context.detail}` : ''}
            </p>
          ))}
        </>
      )}
      {row.approvals.length > 0 && (
        <button
          type="button"
          onClick={onOpenApprovals}
          className="pointer-coarse:min-h-11 cursor-pointer rounded-pill bg-gold px-4 py-2 text-xs font-semibold tracking-tight text-green-house transition-all duration-200 ease-in-out hover:opacity-90 active:scale-[0.98]"
        >
          Review approval
        </button>
      )}
    </div>
  )
}

function RowActions({
  row,
  onOpenRescue,
}: {
  row: TodayRow
  onOpenRescue?: (rescueId: string) => void
}) {
  if (row.rescue === undefined) {
    return <span className="text-sm text-text-secondary">—</span>
  }
  return (
    <button
      type="button"
      onClick={() => onOpenRescue?.(row.rescue!.id)}
      className="pointer-coarse:min-h-11 cursor-pointer rounded-pill border border-black/10 bg-surface px-4 py-2 text-xs font-semibold tracking-tight text-text-primary transition-all duration-200 ease-in-out hover:opacity-90 active:scale-[0.98]"
    >
      View detail
    </button>
  )
}

/** Employee cell: assigned name, "Unassigned" when open, "(absent)" marker. */
function EmployeeName({ shift }: { shift: Shift }) {
  if (shift.assigneeName === null) {
    return <span className="text-text-secondary">Unassigned</span>
  }
  return (
    <span>
      {shift.assigneeName}
      {shift.status === 'absent' ? ' (absent)' : null}
    </span>
  )
}

const HEAD_CELLS = ['Role', 'Window', 'Employee', 'Status', 'Rescue', 'Actions'] as const

export interface TodayScreenProps {
  /** Injected clock for deterministic tests; defaults to now. */
  now?: Date
  /** Called with the rescue id when the user opens a rescue from a row. */
  onOpenRescue?: (rescueId: string) => void
  /** Called when the user asks to review approvals. */
  onOpenApprovals?: () => void
}

export function TodayScreen({ now = new Date(), onOpenRescue, onOpenApprovals }: TodayScreenProps) {
  const dayIso = now.toISOString().slice(0, 10)
  const { shifts, isLoading } = useTodayShifts(dayIso)
  const { rescues } = useActiveRescues()
  const { approvals } = usePendingApprovals()

  const rows = buildTodayRows(shifts ?? [], rescues ?? [], approvals ?? [], RoleOrder)

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <h1 className="font-serif text-4xl font-semibold tracking-tight text-green-starbucks">
            Today
          </h1>
          <p className="text-base tracking-tight text-text-secondary">{formatLongDate(now)}</p>
        </div>
        <span className="flex items-center gap-2 rounded-pill border border-error bg-surface px-4 py-2 text-sm font-semibold tracking-tight text-error">
          <span className="size-2 rounded-full bg-error" />
          {rescues?.length ?? 0} active rescues
        </span>
      </div>

      {isLoading ? (
        <p className="text-base text-text-secondary">Loading…</p>
      ) : (
        <>
          {/* Phone: one card per shift. */}
          <ul
            data-testid="today-cards"
            aria-label="Today's shifts"
            className="space-y-3 md:hidden"
          >
            {rows.map((row) => (
              <li
                key={row.shift.id}
                className="rounded-card bg-surface px-4 py-3 shadow-card"
              >
                <div className="flex items-baseline justify-between gap-3">
                  <p className="text-base font-semibold tracking-tight">
                    {roleLabels[row.shift.role]}
                  </p>
                  <p className="text-sm tracking-tight text-text-secondary">
                    {formatShiftTime(row.shift, TIMEZONE)}
                  </p>
                </div>
                <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm tracking-tight">
                    <EmployeeName shift={row.shift} />
                    <span className="text-text-secondary"> · {statusLabels[row.shift.status]}</span>
                  </p>
                  <RescueBadge state={row.state} />
                </div>
                <div className="mt-2">
                  <RescueCell
                    row={row}
                    now={now}
                    onOpenRescue={onOpenRescue}
                    onOpenApprovals={onOpenApprovals}
                  />
                </div>
                <div className="mt-2">
                  <RowActions row={row} onOpenRescue={onOpenRescue} />
                </div>
              </li>
            ))}
          </ul>

          {/* Tablet and up: the dashboard table. */}
          <div
            data-testid="today-table"
            className="hidden overflow-x-auto rounded-card bg-surface px-4 py-2 shadow-card md:block"
          >
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-black/5 text-xs uppercase tracking-wider text-text-secondary">
                  {HEAD_CELLS.map((cell) => (
                    <th key={cell} className="py-3 pr-4 font-medium">
                      {cell}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.shift.id} className="border-b border-black/5 align-top last:border-0">
                    <td className="py-3 pr-4 text-sm font-semibold tracking-tight">
                      {roleLabels[row.shift.role]}
                    </td>
                    <td className="py-3 pr-4 text-sm tracking-tight text-text-secondary">
                      {formatShiftTime(row.shift, TIMEZONE)}
                    </td>
                    <td className="py-3 pr-4 text-sm tracking-tight">
                      <EmployeeName shift={row.shift} />
                    </td>
                    <td className="py-3 pr-4 text-sm tracking-tight text-text-secondary">
                      {statusLabels[row.shift.status]}
                    </td>
                    <td className="py-3 pr-4">
                      <RescueCell
                        row={row}
                        now={now}
                        onOpenRescue={onOpenRescue}
                        onOpenApprovals={onOpenApprovals}
                      />
                    </td>
                    <td className="py-3">
                      <RowActions row={row} onOpenRescue={onOpenRescue} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
