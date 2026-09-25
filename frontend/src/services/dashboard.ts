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
  fetchActiveRescues,
  fetchAgentDecisions,
  fetchConversationThread,
  fetchConversations,
  fetchDemoClock,
  fetchOpsMetrics,
  fetchRescueDetail,
  fetchSettings,
  fetchSimulatorEmployees,
  fetchSystemStatus,
  resetDemoClock,
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
 * broker timers keep their real-time ETA. `reset` zeroes the offset — a
 * leftover advance silently moves "now" for the whole worker. */
export function useDemoClock(): {
  time: string | undefined
  offsetSeconds: number | undefined
  /** Virtual "now" as a Date, for computing roster situations. */
  virtualNow: Date | undefined
  advance: (seconds: number) => void
  reset: () => void
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
  const invalidateBoards = () => {
    // Deadlines and escalations moved: the Today board and every thread
    // reflect the new virtual time on the next render.
    void queryClient.invalidateQueries({ queryKey: ['shifts'] })
    void queryClient.invalidateQueries({ queryKey: ['rescues'] })
    void queryClient.invalidateQueries({ queryKey: ['conversations'] })
  }
  const advanceMutation = useMutation({
    mutationFn: (seconds: number) => advanceDemoClock(seconds),
    onSuccess: (clock) => {
      queryClient.setQueryData(['demo-clock'], clock)
      invalidateBoards()
    },
  })
  const resetMutation = useMutation({
    mutationFn: () => resetDemoClock(),
    onSuccess: (clock) => {
      queryClient.setQueryData(['demo-clock'], clock)
      invalidateBoards()
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
    advanceMutation.mutate(seconds)
  }
  const reset = () => {
    if (mockMode) {
      // Back to the documented mock demo time.
      setMockTime('15:11')
      return
    }
    resetMutation.mutate()
  }
  return {
    time: mockMode ? mockTime : (query.data ? formatVirtualTime(query.data.now) : undefined),
    offsetSeconds: mockMode ? 0 : query.data?.offsetSeconds,
    virtualNow: query.data ? new Date(query.data.now) : undefined,
    advance,
    reset,
    isAdvancing: advanceMutation.isPending || resetMutation.isPending,
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

// --- Acceptance-race scenario (spec §7.6): the honest concurrency demo -------

/** What the demo employees reply to accept: the same answer the
 * acceptance-race integration test uses, so the agent reads an acceptance. */
const SCENARIO_ACCEPTANCE_TEXT = 'sí'

const SCENARIO_READY_HINT =
  'Watch the Today board: exactly one candidate keeps the shift and the other is told it is already covered.'

const SCENARIO_DONE_MESSAGE =
  'Done: one candidate should now hold the shift; the other was told it is already covered.'

type ScenarioTarget =
  | { problem: string }
  | { rescueId: string; candidates: { employeeId: string; employeeName: string }[] }

export type ScenarioStatus = 'loading' | 'ready' | 'running' | 'unavailable'

/**
 * The "two candidates accept at once" demo: it fires both acceptance messages
 * concurrently, so the orchestrator's single-winner invariant is actually
 * exercised on screen instead of described. It finds the active OFFERING
 * rescue with at least two pending offers; anything else is reported
 * honestly instead of silently doing nothing.
 */
export function useAcceptanceRaceScenario(): {
  status: ScenarioStatus
  message: string
  run: () => void
} {
  const queryClient = useQueryClient()
  const mockMode = isMockMode()
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<string | null>(null)

  const query = useQuery({
    queryKey: ['demo-scenario'],
    queryFn: async (): Promise<ScenarioTarget> => {
      const rescues = await fetchActiveRescues()
      const offering = rescues.find((rescue) => rescue.status === 'OFFERING')
      if (!offering) {
        return { problem: 'No active rescue is offering right now: open a rescue first.' }
      }
      const detail = await fetchRescueDetail(offering.id)
      const candidates = detail.offers
        .filter((offer) => offer.status === 'PENDING' && offer.employeeId)
        .map((offer) => ({
          employeeId: offer.employeeId as string,
          employeeName: offer.employeeName,
        }))
      if (candidates.length < 2) {
        return {
          problem: 'The offering rescue has fewer than two pending offers to race.',
        }
      }
      return { rescueId: offering.id, candidates: candidates.slice(0, 2) }
    },
    enabled: !mockMode,
    staleTime: LIVE_STALE_TIME_MS,
  })

  const target = query.data
  let status: ScenarioStatus
  let message: string
  if (mockMode) {
    status = 'unavailable'
    message = 'The scenario runs in live mode: start the stack and open this screen again.'
  } else if (running) {
    status = 'running'
    message = 'Both candidates are answering at the same time…'
  } else if (result !== null) {
    status = 'unavailable'
    message = result
  } else if (query.isPending) {
    status = 'loading'
    message = ''
  } else if (target !== undefined && 'problem' in target) {
    status = 'unavailable'
    message = target.problem
  } else {
    status = 'ready'
    message = SCENARIO_READY_HINT
  }

  const run = () => {
    if (mockMode || running || target === undefined || 'problem' in target) {
      return
    }
    setRunning(true)
    setResult(null)
    // Both sends fire together: awaiting the first before starting the second
    // would decide the winner by order and make the race meaningless.
    void Promise.allSettled(
      target.candidates.map((candidate) =>
        sendSimulatorMessage(candidate.employeeId, SCENARIO_ACCEPTANCE_TEXT),
      ),
    ).then(() => {
      setRunning(false)
      setResult(SCENARIO_DONE_MESSAGE)
      // The worker settled the race: every board that shows its outcome
      // refetches, and the scenario re-evaluates the (now settled) rescue.
      void queryClient.invalidateQueries({ queryKey: ['rescues'] })
      void queryClient.invalidateQueries({ queryKey: ['shifts'] })
      void queryClient.invalidateQueries({ queryKey: ['approvals'] })
      void queryClient.invalidateQueries({ queryKey: ['conversations'] })
      void queryClient.invalidateQueries({ queryKey: ['demo-scenario'] })
    })
  }

  return { status, message, run }
}
