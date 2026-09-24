import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Button } from './components/ui/Button'
import { RescueDetailScreen } from './screens/RescueDetailScreen'
import { TodayScreen } from './screens/TodayScreen'

const queryClient = new QueryClient()

/**
 * Themed app shell for the Shift Rescue manager dashboard.
 * Canvas, greens, typography and elevation follow DESIGN.md.
 * Navigation is state-based (selected rescue); a router lands when the
 * number of screens justifies it.
 */
function Shell() {
  const [selectedRescueId, setSelectedRescueId] = useState<string | null>(null)

  return (
    <div className="min-h-screen bg-canvas font-sans text-text-primary">
      <header
        role="banner"
        className="sticky top-0 z-10 flex h-16 items-center justify-between border-b border-black/5 bg-white px-4 shadow-nav md:h-[72px] md:px-6"
      >
        <span className="text-lg font-semibold tracking-tight text-green-starbucks">
          Shift Rescue
        </span>
        <nav className="flex items-center gap-2">
          <Button variant="secondary">Sign in</Button>
          <Button variant="dark">Join now</Button>
        </nav>
      </header>
      <main className="mx-auto w-full max-w-6xl px-4 py-8 md:px-6">
        {selectedRescueId ? (
          <RescueDetailScreen
            rescueId={selectedRescueId}
            onBack={() => setSelectedRescueId(null)}
          />
        ) : (
          <TodayScreen onOpenRescue={setSelectedRescueId} />
        )}
      </main>
    </div>
  )
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Shell />
    </QueryClientProvider>
  )
}
