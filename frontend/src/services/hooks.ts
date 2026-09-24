import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ApprovalRequest, RescueCase, RescueDetail, Shift } from '../domain/types'
import { MockDashboardDataSource, type DashboardDataSource } from './mock'

/**
 * Single source instance for the app; swap for the API-backed implementation
 * when the backend lands. Components never import the mock directly.
 */
export const dataSource: DashboardDataSource = new MockDashboardDataSource()

export function useTodayShifts(dayIso: string): { shifts: Shift[] | undefined; isLoading: boolean } {
  const query = useQuery({
    queryKey: ['shifts', dayIso],
    queryFn: () => dataSource.getShifts(dayIso),
  })
  return { shifts: query.data, isLoading: query.isLoading }
}

export function useActiveRescues(): { rescues: RescueCase[] | undefined; isLoading: boolean } {
  const query = useQuery({
    queryKey: ['rescues', 'active'],
    queryFn: () => dataSource.getActiveRescues(),
  })
  return { rescues: query.data, isLoading: query.isLoading }
}

export function useRescueDetail(rescueId: string): { detail: RescueDetail | undefined; isLoading: boolean } {
  const query = useQuery({
    queryKey: ['rescues', rescueId],
    queryFn: () => dataSource.getRescueDetail(rescueId),
  })
  return { detail: query.data, isLoading: query.isLoading }
}

export function usePendingApprovals(): { approvals: ApprovalRequest[] | undefined; isLoading: boolean } {
  const query = useQuery({
    queryKey: ['approvals', 'pending'],
    queryFn: () => dataSource.getPendingApprovals(),
  })
  return { approvals: query.data, isLoading: query.isLoading }
}

export function useDecideApproval(): {
  decide: (id: string, decision: 'approved' | 'rejected') => void
  isPending: boolean
} {
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: 'approved' | 'rejected' }) =>
      dataSource.decideApproval(id, decision, 'manager_01'),
    onSuccess: () => {
      // The decision also affects the rescue detail (approval timeline).
      void queryClient.invalidateQueries({ queryKey: ['approvals'] })
      void queryClient.invalidateQueries({ queryKey: ['rescues'] })
    },
  })
  return { decide: (id, decision) => mutation.mutate({ id, decision }), isPending: mutation.isPending }
}
