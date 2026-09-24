import { useQuery } from '@tanstack/react-query'
import type { RescueCase, Shift } from '../domain/types'
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
