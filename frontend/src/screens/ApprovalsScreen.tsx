import { approvalKindLabel, orderApprovalsByOldest } from '../domain/approvals'
import type { ApprovalRequest } from '../domain/types'
import { useDecideApproval, usePendingApprovals } from '../services/hooks'

function ApprovalItem({ approval }: { approval: ApprovalRequest }) {
  const { decide, isPending } = useDecideApproval()
  const description = approval.context.detail
    ? `${approval.context.employeeName} — ${approval.context.detail}`
    : `${approval.context.employeeName}, shift ${approval.context.shiftTime}`
  return (
    <li className="flex flex-wrap items-center justify-between gap-4 rounded-card bg-surface px-4 py-4 shadow-card md:px-6">
      <div className="flex items-start gap-3">
        <span className="mt-1.5 size-2 shrink-0 rounded-full bg-gold" aria-hidden />
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">
            {approvalKindLabel(approval.kind)}
          </p>
          <p className="mt-0.5 text-base tracking-tight text-text-primary">{description}</p>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <button
          type="button"
          disabled={isPending}
          onClick={() => decide(approval.id, 'rejected')}
          className="pointer-coarse:min-h-11 cursor-pointer rounded-pill border border-black/15 bg-transparent px-5 py-2 text-sm font-semibold tracking-tight text-text-primary transition-all duration-200 hover:bg-black/5 active:scale-95 disabled:opacity-50"
        >
          Reject
        </button>
        <button
          type="button"
          disabled={isPending}
          onClick={() => decide(approval.id, 'approved')}
          className="pointer-coarse:min-h-11 cursor-pointer rounded-pill bg-green-accent px-6 py-2 text-sm font-semibold tracking-tight text-white transition-all duration-200 hover:opacity-90 active:scale-95 disabled:opacity-50"
        >
          Approve
        </button>
      </div>
    </li>
  )
}

/**
 * Approvals inbox (spec §7.6 screen 3, mockup "Aprobaciones"): oldest first,
 * kind label + context per card, approve/reject decisions.
 */
export function ApprovalsScreen() {
  const { approvals, isLoading } = usePendingApprovals()

  return (
    <div className="space-y-6">
      <div className="flex items-baseline gap-3">
        <h1 className="font-serif text-4xl font-semibold tracking-tight text-green-starbucks">
          Approvals
        </h1>
        {approvals && approvals.length > 0 && (
          <span className="text-sm text-text-secondary">
            {approvals.length} pending
          </span>
        )}
      </div>
      {isLoading ? (
        <p className="text-base text-text-secondary">Loading…</p>
      ) : !approvals || approvals.length === 0 ? (
        <p className="text-base text-text-secondary">No pending approvals</p>
      ) : (
        <ul className="space-y-3">
          {orderApprovalsByOldest(approvals).map((approval) => (
            <ApprovalItem key={approval.id} approval={approval} />
          ))}
        </ul>
      )}
    </div>
  )
}
