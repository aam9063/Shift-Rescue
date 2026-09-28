import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppHeader, Fab, type AppView } from './components/AppHeader'
import { ApprovalsScreen } from './screens/ApprovalsScreen'
import { RescueDetailScreen } from './screens/RescueDetailScreen'
import { SettingsScreen } from './screens/SettingsScreen'
import { TodayScreen } from './screens/TodayScreen'
import { ConversationsScreen } from './screens/ConversationsScreen'
import { OpsScreen } from './screens/OpsScreen'
import { AgentDecisionsScreen } from './screens/AgentDecisionsScreen'
import { EvalsScreen } from './screens/EvalsScreen'
import { SimulatorScreen } from './screens/SimulatorScreen'
import { RequireAuth } from './components/RequireAuth'
import { getSession } from './services/auth'
import { useLiveEvents } from './services/liveEvents'
import { ApiError } from './services/apiClient'
import { usePendingApprovals } from './services/hooks'

/**
 * Retry policy: never replay a client error. A 403 (wrong role) or a 404 answers
 * the same however many times it is asked, so the default three retries only
 * produced three extra red rows in the network tab for nothing. Transient
 * failures (network, 5xx) still get two attempts.
 */
function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false
  return failureCount < 2
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: shouldRetry, refetchOnWindowFocus: true },
    mutations: { retry: false },
  },
})

const VIEWS: readonly AppView[] = [
  'today',
  'approvals',
  'conversations',
  'ops',
  'agentDecisions',
  'evals',
  'settings',
  'simulator',
]

/** The current view is the URL hash, so deep links survive the login round-trip. */
function viewFromHash(): AppView | null {
  const hash = window.location.hash.replace(/^#/, '')
  return (VIEWS as readonly string[]).includes(hash) ? (hash as AppView) : null
}

/**
 * Themed app shell per the user mockups: dark-green header band over the
 * warm cream canvas, text navigation with gold underline, state-based
 * routing (a router lands when the number of screens justifies it).
 */
function Shell({ now, onLogout }: { now?: Date; onLogout: () => void }) {
  const [view, setView] = useState<AppView>(() => viewFromHash() ?? 'today')
  const [selectedRescueId, setSelectedRescueId] = useState<string | null>(null)
  const { approvals } = usePendingApprovals()
  const manager = getSession()?.manager
  // Live channel (spec §7.5): the screens refetch when the worker reports a
  // change made elsewhere. Its state is shown so it is never a silent promise.
  const liveState = useLiveEvents()

  const navigate = (next: AppView) => {
    setView(next)
    window.location.hash = next
    setSelectedRescueId(null)
  }

  return (
    <div className="min-h-screen bg-canvas font-sans text-text-primary">
      <AppHeader
        currentView={view}
        onNavigate={navigate}
        pendingApprovals={approvals?.filter((a) => a.status === 'pending').length ?? 0}
        managerName={manager?.name}
        managerRole={manager?.role}
        onLogout={onLogout}
      />
      <main className="mx-auto w-full max-w-[1440px] px-4 py-8 md:px-6">
        {liveState !== 'live' ? (
          <p
            role="status"
            className="mb-4 inline-flex items-center gap-2 rounded-pill bg-black/5 px-3 py-1 text-xs font-medium tracking-wide text-text-secondary"
          >
            <span className="size-1.5 rounded-full bg-text-secondary" aria-hidden />
            {liveState === 'connecting' ? 'Connecting to live updates…' : 'Live updates offline'}
          </p>
        ) : null}
        {selectedRescueId ? (
          <RescueDetailScreen
            rescueId={selectedRescueId}
            onBack={() => {
              setSelectedRescueId(null)
              setView('today')
            }}
          />
        ) : view === 'approvals' ? (
          <ApprovalsScreen />
        ) : view === 'conversations' ? (
          <ConversationsScreen />
        ) : view === 'ops' ? (
          <OpsScreen />
        ) : view === 'agentDecisions' ? (
          <AgentDecisionsScreen />
        ) : view === 'evals' ? (
          <EvalsScreen />
        ) : view === 'settings' ? (
          <SettingsScreen />
        ) : view === 'simulator' ? (
          <SimulatorScreen />
        ) : (
          <TodayScreen now={now} onOpenRescue={setSelectedRescueId} />
        )}
      </main>
      <Fab label="Report absence" />
    </div>
  )
}

export interface AppProps {
  /** Injected clock for deterministic tests; defaults to now. */
  now?: Date
}

export function App({ now = new Date() }: AppProps) {
  return (
    <QueryClientProvider client={queryClient}>
      <RequireAuth>
        {(signOut) => <Shell now={now} onLogout={signOut} />}
      </RequireAuth>
    </QueryClientProvider>
  )
}
