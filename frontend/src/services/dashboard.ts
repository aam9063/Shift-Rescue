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
} from './dashboardMock'

/**
 * Mock-backed dashboard data (mockups in public/img). Later slices swap this
 * module for the REST API client; components only consume these hooks.
 */

export function useConversations(): { conversations: Conversation[] } {
  const query = useQuery({
    queryKey: ['conversations'],
    queryFn: async () => CONVERSATIONS,
    staleTime: Infinity,
  })
  return { conversations: query.data ?? [] }
}

export function useAgentDecisions(): { decisions: AgentDecision[] } {
  const query = useQuery({
    queryKey: ['agent-decisions'],
    queryFn: async () => AGENT_DECISIONS,
    staleTime: Infinity,
  })
  return { decisions: query.data ?? [] }
}

export function useEvalRun(): { evalRun: EvalRunSummary | undefined } {
  const query = useQuery({
    queryKey: ['eval-run'],
    queryFn: async () => EVAL_RUN,
    staleTime: Infinity,
  })
  return { evalRun: query.data }
}

export function useOpsMetrics(): { metrics: OpsMetrics | undefined } {
  const query = useQuery({
    queryKey: ['ops-metrics'],
    queryFn: async () => OPS_METRICS,
    staleTime: Infinity,
  })
  return { metrics: query.data }
}

export function useSettings(): {
  settings: LocationSettings
  save: (next: LocationSettings) => void
  saved: boolean
} {
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: ['settings'],
    queryFn: async () => DEFAULT_SETTINGS,
    staleTime: Infinity,
  })
  const mutation = useMutation({
    mutationFn: async (next: LocationSettings) => next,
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
