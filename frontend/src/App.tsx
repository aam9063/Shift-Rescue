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
import { usePendingApprovals } from './services/hooks'

const queryClient = new QueryClient()

/**
 * Themed app shell per the user mockups: dark-green header band over the
 * warm cream canvas, text navigation with gold underline, state-based
 * routing (a router lands when the number of screens justifies it).
 */
function Shell({ now }: { now?: Date }) {
  const [view, setView] = useState<AppView>('today')
  const [selectedRescueId, setSelectedRescueId] = useState<string | null>(null)
  const { approvals } = usePendingApprovals()

  const navigate = (next: AppView) => {
    setView(next)
    setSelectedRescueId(null)
  }

  return (
    <div className="min-h-screen bg-canvas font-sans text-text-primary">
      <AppHeader
        currentView={view}
        onNavigate={navigate}
        pendingApprovals={approvals?.filter((a) => a.status === 'pending').length ?? 0}
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
      <Shell now={now} />
    </QueryClientProvider>
  )
}
