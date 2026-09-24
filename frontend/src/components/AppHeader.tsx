import { Button } from './ui/Button'

export type AppView = 'today' | 'approvals'

export interface AppHeaderProps {
  currentView: AppView
  onNavigate: (view: AppView) => void
  pendingApprovals: number
}

/**
 * Dark House-Green header band per the user mockup: clock logo, wordmark,
 * centered location pill, Approvals nav with pending count and the white
 * "+ Report absence" CTA (DESIGN.md Green-on-Green Inverted treatment).
 */
export function AppHeader({ currentView, onNavigate, pendingApprovals }: AppHeaderProps) {
  return (
    <header role="banner" className="bg-green-house text-white">
      <div className="mx-auto flex h-16 max-w-[1440px] items-center justify-between px-4 md:px-6">
        <div className="flex items-center gap-3">
          <span className="flex size-8 items-center justify-center rounded-full border-2 border-white">
            <svg viewBox="0 0 16 16" className="size-4 fill-white" aria-hidden="true">
              <path d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1Zm0 1.5a5.5 5.5 0 1 1 0 11 5.5 5.5 0 0 1 0-11ZM7.25 4v4.31l3.03 1.8.75-1.23-2.53-1.5V4h-1.25Z" />
            </svg>
          </span>
          <span className="text-lg font-semibold tracking-tight">Shift Rescue</span>
        </div>
        <button
          type="button"
          className="hidden rounded-pill bg-black/20 px-4 py-2 text-sm font-medium tracking-tight transition-colors hover:bg-black/30 md:block"
        >
          La Terraza del Puerto ▾
        </button>
        <div className="flex items-center gap-2">
          <nav className="flex items-center gap-2" aria-label="Main">
            <button
              type="button"
              onClick={() => onNavigate('today')}
              className={`rounded-pill px-4 py-2 text-sm font-semibold tracking-tight transition-colors ${
                currentView === 'today' ? 'bg-white text-green-house' : 'text-white hover:bg-white/10'
              }`}
            >
              Today
            </button>
            <button
              type="button"
              onClick={() => onNavigate('approvals')}
              className={`flex items-center gap-2 rounded-pill px-4 py-2 text-sm font-semibold tracking-tight transition-colors ${
                currentView === 'approvals'
                  ? 'bg-white text-green-house'
                  : 'text-white hover:bg-white/10'
              }`}
            >
              Approvals
              {pendingApprovals > 0 && (
                <span className="flex size-5 items-center justify-center rounded-full bg-gold text-xs font-bold text-green-house">
                  {pendingApprovals}
                </span>
              )}
            </button>
          </nav>
          <Button variant="onDark" className="!bg-white !text-green-accent !border-white">
            + Report absence
          </Button>
        </div>
      </div>
    </header>
  )
}
