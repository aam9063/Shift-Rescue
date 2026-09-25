import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import {
  AGENT_DECISIONS,
  CONVERSATIONS,
  DEFAULT_SETTINGS,
  EVAL_RUN,
  OPS_METRICS,
  type AgentDecision,
  type ChatMessage,
  type Conversation,
  type EvalRunSummary,
  type LocationSettings,
  type OpsMetrics,
  type SystemStatus,
  systemStatusSource,
} from './dashboardMock'
import {
  advanceDemoClock,
  fetchAgentDecisions,
  fetchConversationThread,
  fetchConversations,
  fetchDemoClock,
  fetchOpsMetrics,
  fetchSettings,
  fetchSimulatorEmployees,
  fetchSystemStatus,
  saveSettings,
  sendSimulatorMessage,
} from './api'
import { isMockMode } from './dataSource'
import type { SimulatorEmployee } from '../domain/types'

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

export function useAgentDecisions(): {
  decisions: AgentDecision[]
  error: unknown
  isLoading: boolean
} {
  const query = useQuery({
    queryKey: ['agent-decisions'],
    queryFn: isMockMode() ? async () => AGENT_DECISIONS : fetchAgentDecisions,
    staleTime: isMockMode() ? Infinity : LIVE_STALE_TIME_MS,
  })
  // The endpoint is operator-only (spec §7.5), so a manager gets a 403 here:
  // the screen must say so instead of rendering an empty table that looks broken.
  return { decisions: query.data ?? [], error: query.error, isLoading: query.isLoading }
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

// --- Demo simulator (spec §7.6): real roster, threads and shared clock -------

/** The roster behind `VITE_USE_MOCK`: the mock conversations, mapped. */
function mockEmployees(): SimulatorEmployee[] {
  return CONVERSATIONS.map((conversation) => ({
    id: conversation.employeeId,
    displayName: conversation.employeeName,
    roles: [],
    shiftStartsAt: null,
    shiftEndsAt: null,
    shiftStatus: null,
    conversationId: conversation.employeeId,
  }))
}

export function useDemoEmployees(): { employees: SimulatorEmployee[] } {
  const query = useQuery({
    queryKey: ['demo-employees'],
    queryFn: isMockMode() ? mockEmployees : fetchSimulatorEmployees,
    staleTime: isMockMode() ? Infinity : LIVE_STALE_TIME_MS,
  })
  return { employees: query.data ?? [] }
}

export function useDemoThread(conversationId: string | null): { messages: ChatMessage[] } {
  const mockMode = isMockMode()
  const query = useQuery({
    queryKey: ['demo-thread', conversationId],
    queryFn: mockMode
      ? async () => CONVERSATIONS.find((c) => c.employeeId === conversationId)?.messages ?? []
      : () => fetchConversationThread(conversationId as string),
    enabled: conversationId !== null,
    staleTime: mockMode ? Infinity : LIVE_STALE_TIME_MS,
  })
  return { messages: query.data ?? [] }
}

/** The demo clock (spec §7.5): the shared virtual time, advanced in Redis in
 * live mode and locally in mock mode. The UI states the honest limitation:
 * broker timers keep their real-time ETA. */
export function useDemoClock(): {
  time: string | undefined
  advance: (seconds: number) => void
  isAdvancing: boolean
} {
  const queryClient = useQueryClient()
  const mockMode = isMockMode()
  const [mockTime, setMockTime] = useState('15:11')
  const query = useQuery({
    queryKey: ['demo-clock'],
    queryFn: fetchDemoClock,
    enabled: !mockMode,
    staleTime: 0,
  })
  const mutation = useMutation({
    mutationFn: (seconds: number) => advanceDemoClock(seconds),
    onSuccess: (clock) => {
      queryClient.setQueryData(['demo-clock'], clock)
      // Deadlines and escalations moved: the Today board and every thread
      // reflect the new virtual time on the next render.
      void queryClient.invalidateQueries({ queryKey: ['shifts'] })
      void queryClient.invalidateQueries({ queryKey: ['rescues'] })
      void queryClient.invalidateQueries({ queryKey: ['conversations'] })
    },
  })
  const advance = (seconds: number) => {
    if (mockMode) {
      setMockTime((current) => {
        const [h, m] = current.split(':').map(Number)
        const total = h * 60 + m + Math.round(seconds / 60)
        return `${String(Math.floor(total / 60) % 24).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
      })
      return
    }
    mutation.mutate(seconds)
  }
  return {
    time: mockMode ? mockTime : (query.data ? formatVirtualTime(query.data.now) : undefined),
    advance,
    isAdvancing: mutation.isPending,
  }
}

export function useSendDemoMessage(): {
  send: (employeeId: string, conversationId: string | null, text: string) => void
  isPending: boolean
} {
  const queryClient = useQueryClient()
  const mockMode = isMockMode()
  const mutation = useMutation({
    mutationFn: ({
      employeeId,
      text,
    }: {
      employeeId: string
      conversationId: string | null
      text: string
    }) => sendSimulatorMessage(employeeId, text),
    onSuccess: (_sid, variables) => {
      // The worker applies the message: refetch the thread, the roster (the
      // conversation id appears on first contact) and the Today board.
      if (variables.conversationId) {
        void queryClient.invalidateQueries({
          queryKey: ['demo-thread', variables.conversationId],
        })
      }
      void queryClient.invalidateQueries({ queryKey: ['demo-employees'] })
      void queryClient.invalidateQueries({ queryKey: ['conversations'] })
      void queryClient.invalidateQueries({ queryKey: ['shifts'] })
      void queryClient.invalidateQueries({ queryKey: ['rescues'] })
    },
  })
  const send = (employeeId: string, conversationId: string | null, text: string) => {
    if (mockMode) {
      // Offline demo: append locally so the thread still feels alive.
      queryClient.setQueryData<ChatMessage[]>(
        ['demo-thread', conversationId],
        (current) => [...(current ?? []), { from: 'employee', text }],
      )
      return
    }
    mutation.mutate({ employeeId, conversationId, text })
  }
  return { send, isPending: mutation.isPending }
}

/** The demo clock is UTC; show HH:MM without a timezone debate. */
function formatVirtualTime(iso: string): string {
  return iso.slice(11, 16)
}
