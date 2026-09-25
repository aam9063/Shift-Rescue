import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  AGENT_DECISIONS,
  CONVERSATIONS,
  DEFAULT_SETTINGS,
  EVAL_RUN,
  OPS_METRICS,
  type AgentDecision,
  type Conversation,
  type EvalRunSummary,
  type LocationSettings,
  type OpsMetrics,
  type SystemStatus,
  systemStatusSource,
} from './dashboardMock'
import {
  fetchAgentDecisions,
  fetchConversations,
  fetchOpsMetrics,
  fetchSettings,
  fetchSystemStatus,
  saveSettings,
} from './api'
import { isMockMode } from './dataSource'

/**
 * Second data layer hooks (conversations, agent decisions, Ops metrics,
 * settings, system status). Live data comes from the API; in mock mode the
 * `dashboardMock` constants keep the screens working offline and hermetic in
 * tests. Query keys and result shapes stay compatible with the screens.
 */

const LIVE_STALE_TIME_MS = 30_000

export function useConversations(): { conversations: Conversation[] } {
  const query = useQuery({
    queryKey: ['conversations'],
    queryFn: isMockMode() ? async () => CONVERSATIONS : fetchConversations,
    staleTime: isMockMode() ? Infinity : LIVE_STALE_TIME_MS,
  })
  return { conversations: query.data ?? [] }
}

export function useAgentDecisions(): { decisions: AgentDecision[] } {
  const query = useQuery({
    queryKey: ['agent-decisions'],
    queryFn: isMockMode() ? async () => AGENT_DECISIONS : fetchAgentDecisions,
    staleTime: isMockMode() ? Infinity : LIVE_STALE_TIME_MS,
  })
  return { decisions: query.data ?? [] }
}

export function useEvalRun(): { evalRun: EvalRunSummary | undefined } {
  const query = useQuery({
    // No `/api/evals/runs*` endpoint exists yet: the Evals screen stays on
    // mock data and says so in the UI.
    queryKey: ['eval-run'],
    queryFn: async () => EVAL_RUN,
    staleTime: Infinity,
  })
  return { evalRun: query.data }
}

export function useOpsMetrics(): { metrics: OpsMetrics | undefined } {
  const query = useQuery({
    queryKey: ['ops-metrics'],
    queryFn: isMockMode() ? async () => OPS_METRICS : fetchOpsMetrics,
    staleTime: isMockMode() ? Infinity : LIVE_STALE_TIME_MS,
  })
  return { metrics: query.data }
}

export function useSettings(): {
  settings: LocationSettings
  save: (next: LocationSettings) => void
  saved: boolean
} {
  const queryClient = useQueryClient()
  const mockMode = isMockMode()
  const query = useQuery({
    queryKey: ['settings'],
    queryFn: mockMode ? async () => DEFAULT_SETTINGS : fetchSettings,
    staleTime: mockMode ? Infinity : LIVE_STALE_TIME_MS,
  })
  const mutation = useMutation({
    mutationFn: mockMode
      ? async (next: LocationSettings) => next
      : async (next: LocationSettings) => saveSettings(next),
    onSuccess: (saved) => {
      queryClient.setQueryData(['settings'], saved)
    },
  })
  return {
    settings: query.data ?? DEFAULT_SETTINGS,
    save: (next) => mutation.mutate(next),
    saved: mutation.isSuccess,
  }
}

export function useSystemStatus(): { status: SystemStatus | undefined } {
  const query = useQuery({
    queryKey: ['system-status'],
    // `/api/status` is public, so the degraded banner works pre-login too.
    queryFn: isMockMode() ? () => systemStatusSource.get() : fetchSystemStatus,
    staleTime: 0,
  })
  return { status: query.data }
}
