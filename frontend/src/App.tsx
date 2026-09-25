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
import { usePendingApprovals } from './services/hooks'

const queryClient = new QueryClient()

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
