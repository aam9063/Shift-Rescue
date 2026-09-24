import {
  approvalKindLabel,
  orderApprovalsByOldest,
} from '../domain/approvals'
import type { ApprovalRequest } from '../domain/types'
import { useDecideApproval, usePendingApprovals } from '../services/hooks'

function ApprovalItem({ approval }: { approval: ApprovalRequest }) {
  const { decide, isPending } = useDecideApproval()
  return (
    <li className="rounded-card bg-surface px-4 py-3 shadow-card">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-base font-semibold tracking-tight">
            {approvalKindLabel(approval.kind)} — {approval.context.employeeName}
          </p>
          <p className="text-sm tracking-tight text-text-secondary">
            Shift {approval.context.shiftTime}
          </p>
          {approval.context.detail && (
            <p className="mt-1 text-sm tracking-tight text-text-secondary">
              {approval.context.detail}
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            disabled={isPending}
            onClick={() => decide(approval.id, 'approved')}
            className="rounded-pill border border-green-accent bg-green-accent px-4 py-[7px] text-sm font-semibold tracking-tight text-white transition-all duration-200 ease-in-out hover:opacity-90 active:scale-95 disabled:opacity-50"
          >
            Approve
          </button>
          <button
            type="button"
            disabled={isPending}
            onClick={() => decide(approval.id, 'rejected')}
            className="rounded-pill border border-error bg-transparent px-4 py-[7px] text-sm font-semibold tracking-tight text-error transition-all duration-200 ease-in-out hover:bg-error/5 active:scale-95 disabled:opacity-50"
          >
            Reject
          </button>
        </div>
      </div>
    </li>
  )
}

/**
 * Pending approvals inbox (spec §7.6 screen 3). Approve and reject are the
 * only human decisions the domain requires before assigning a shift.
 */
export function ApprovalsScreen() {
  const { approvals, isLoading } = usePendingApprovals()

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold leading-9 tracking-tight text-green-starbucks">
        Approvals
      </h1>
      {isLoading ? (
        <p className="text-base text-text-secondary">Loading…</p>
      ) : !approvals || approvals.length === 0 ? (
        <p className="text-base text-text-secondary">No pending approvals</p>
      ) : (
        <ul className="space-y-2">
          {orderApprovalsByOldest(approvals).map((approval) => (
            <ApprovalItem key={approval.id} approval={approval} />
          ))}
        </ul>
      )}
    </div>
  )
}
