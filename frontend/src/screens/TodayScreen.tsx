import type { ReactNode } from 'react'
import { buildTodayColumns, formatCountdown, formatShiftTime } from '../domain/today'
import {
  type ApprovalRequest,
  type OfferPreview,
  type RescueCase,
  type Shift,
  type ShiftRole,
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

const previewDotClasses: Record<OfferPreview['status'], string> = {
  pending: 'bg-green-accent',
  accepted: 'bg-green-accent',
  declined: 'bg-error',
}

const previewStatusLabel: Record<OfferPreview['status'], string> = {
  pending: 'pending',
  accepted: 'accepted',
  declined: 'declined',
}

function formatLongDate(now: Date): string {
  return new Intl.DateTimeFormat('en-GB', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    timeZone: TIMEZONE,
  }).format(now)
}

function shiftOf(rescue: RescueCase, shifts: Shift[]): Shift | undefined {
  return shifts.find((s) => s.id === rescue.shiftId)
}

function Column({
  title,
  count,
  accent,
  children,
}: {
  title: string
  count: number
  accent?: string
  children: ReactNode
}) {
  return (
    <section aria-label={title} className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className={`text-base font-semibold tracking-tight ${accent ?? 'text-text-primary'}`}>
          {title}
        </h2>
        <span className="flex size-5 items-center justify-center rounded-full bg-black/10 text-xs font-semibold text-text-secondary">
          {count}
        </span>
      </div>
      <div className="space-y-3">{children}</div>
    </section>
  )
}

function Card({ topAccent, children }: { topAccent?: string; children: ReactNode }) {
  return (
    <div className={`overflow-hidden rounded-card bg-surface shadow-card ${topAccent ?? ''}`}>
      {children}
    </div>
  )
}

function UncoveredCard({ shift }: { shift: Shift }) {
  return (
    <Card>
      <div className="px-4 py-3">
        <div className="flex items-baseline justify-between">
          <p className="text-base font-semibold tracking-tight">{roleLabels[shift.role]}</p>
          <p className="text-sm tracking-tight text-text-secondary">
            {formatShiftTime(shift, TIMEZONE)}
          </p>
        </div>
        <p className="mt-1 text-sm tracking-tight text-text-secondary">
          No candidates offered yet.
        </p>
      </div>
    </Card>
  )
}

function SeekingCard({
  rescue,
  shift,
  now,
  onOpen,
}: {
  rescue: RescueCase
  shift: Shift | undefined
  now: Date
  onOpen?: () => void
}) {
  const countdown = formatCountdown(rescue.deadlineAt, now)
  const urgent = rescueCountdownUrgent(rescue.deadlineAt, now)
  return (
    <button type="button" onClick={onOpen} className="block w-full cursor-pointer text-left">
      <Card topAccent="border-t-4 border-green-accent">
        <div className="px-4 py-3">
          <div className="flex items-baseline justify-between">
            <p className="text-base font-semibold tracking-tight">
              {shift ? roleLabels[shift.role] : 'Shift'}
            </p>
            <p className="text-sm tracking-tight text-text-secondary">
              {shift ? formatShiftTime(shift, TIMEZONE) : ''}
            </p>
          </div>
          <p className={`mt-1 text-3xl font-bold tracking-tight ${urgent ? 'text-error' : 'text-text-primary'}`}>
            {countdown}
          </p>
          <p className="mt-1 text-sm tracking-tight text-text-secondary">
            Absent: {rescue.absentEmployeeName}
            {rescue.waveCurrent != null && rescue.waveTotal != null && (
              <> — wave {rescue.waveCurrent} of {rescue.waveTotal}.</>
            )}
          </p>
          <ul className="mt-2 space-y-1">
            {rescue.offerPreviews?.map((preview) => (
              <li key={preview.employeeName} className="flex items-center justify-between text-sm tracking-tight">
                <span className="flex items-center gap-2">
                  <span className={`size-2 rounded-full ${previewDotClasses[preview.status]}`} />
                  {preview.employeeName}
                </span>
                <span className="text-text-secondary">{previewStatusLabel[preview.status]}</span>
              </li>
            ))}
          </ul>
        </div>
      </Card>
    </button>
  )
}

function rescueCountdownUrgent(deadlineAt: string, now: Date): boolean {
  const msLeft = new Date(deadlineAt).getTime() - now.getTime()
  return msLeft <= 5 * 60_000
}

function ApprovalCard({
  approval,
  now,
  onReview,
}: {
  approval: ApprovalRequest
  now: Date
  onReview?: () => void
}) {
  const deadline = approvalExpiresAt(approval)
  return (
    <Card topAccent="border-t-4 border-gold">
      <div className="px-4 py-3">
        <div className="flex items-baseline justify-between">
          <p className="text-base font-semibold tracking-tight">
            {approvalKindLabel(approval.kind)}
          </p>
          <p className="text-sm tracking-tight text-text-secondary">
            {approval.context.shiftTime}
          </p>
        </div>
        <p className="mt-1 text-3xl font-bold tracking-tight text-text-primary">
          {deadline ? formatCountdown(deadline, now) : '--:--'}
        </p>
        <p className="mt-1 text-sm tracking-tight text-text-secondary">
          {approval.context.employeeName}
          {approval.context.detail ? ` — ${approval.context.detail}` : ''}
        </p>
        <button
          type="button"
          onClick={onReview}
          className="mt-3 w-full cursor-pointer rounded-pill bg-gold px-4 py-2 text-sm font-semibold tracking-tight text-green-house transition-all duration-200 ease-in-out hover:opacity-90 active:scale-[0.98]"
        >
          Review approval
        </button>
      </div>
    </Card>
  )
}

function approvalExpiresAt(approval: ApprovalRequest): string | undefined {
  return approval.expiresAt
}

function CoveredCard({ shift }: { shift: Shift }) {
  return (
    <Card topAccent="border-t-4 border-green-accent">
      <div className="px-4 py-3">
        <p className="text-base font-semibold tracking-tight">
          {roleLabels[shift.role]} · {formatShiftTime(shift, TIMEZONE).replace(' – ', '-')}
        </p>
        <p className="mt-1 text-sm tracking-tight text-text-secondary">
          Covered by {shift.assigneeName}
        </p>
      </div>
    </Card>
  )
}

export interface TodayScreenProps {
  /** Injected clock for deterministic tests; defaults to now. */
  now?: Date
  /** Called with the rescue id when the user opens a rescue from a card. */
  onOpenRescue?: (rescueId: string) => void
  /** Called when the user asks to review approvals. */
  onOpenApprovals?: () => void
}

export function TodayScreen({ now = new Date(), onOpenRescue, onOpenApprovals }: TodayScreenProps) {
  const dayIso = now.toISOString().slice(0, 10)
  const { shifts, isLoading } = useTodayShifts(dayIso)
  const { rescues } = useActiveRescues()
  const { approvals } = usePendingApprovals()

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
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-4">
          <Column title="Uncovered" count={columns(shifts, rescues, approvals).uncovered.length}>
            {columns(shifts, rescues, approvals).uncovered.map((shift) => (
              <UncoveredCard key={shift.id} shift={shift} />
            ))}
          </Column>
          <Column title="Searching" count={columns(shifts, rescues, approvals).seeking.length}>
            {columns(shifts, rescues, approvals).seeking.map((rescue) => (
              <SeekingCard
                key={rescue.id}
                rescue={rescue}
                shift={shiftOf(rescue, shifts ?? [])}
                now={now}
                onOpen={() => onOpenRescue?.(rescue.id)}
              />
            ))}
          </Column>
          <Column
            title="Needs your approval"
            count={columns(shifts, rescues, approvals).needsApproval.length}
          >
            {columns(shifts, rescues, approvals).needsApproval.map((approval) => (
              <ApprovalCard key={approval.id} approval={approval} now={now} onReview={onOpenApprovals} />
            ))}
          </Column>
          <Column title="Covered today" count={columns(shifts, rescues, approvals).covered.length}>
            {columns(shifts, rescues, approvals).covered.map((shift) => (
              <CoveredCard key={shift.id} shift={shift} />
            ))}
          </Column>
        </div>
      )}
    </div>
  )
}

function columns(
  shifts: Shift[] | undefined,
  rescues: RescueCase[] | undefined,
  approvals: ApprovalRequest[] | undefined,
) {
  return buildTodayColumns(shifts ?? [], rescues ?? [], approvals ?? [])
}
