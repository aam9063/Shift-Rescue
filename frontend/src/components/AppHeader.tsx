import type { ReactNode } from 'react'

export type AppView =
  | 'today'
  | 'approvals'
  | 'conversations'
  | 'ops'
  | 'agentDecisions'
  | 'evals'
  | 'settings'
  | 'simulator'

const MAIN_NAV: { view: AppView; label: string }[] = [
  { view: 'today', label: 'Today' },
  { view: 'approvals', label: 'Approvals' },
  { view: 'conversations', label: 'Conversations' },
  { view: 'ops', label: 'Operations' },
]

const OPERATOR_NAV: { view: AppView; label: string }[] = [
  { view: 'ops', label: 'Ops' },
  { view: 'agentDecisions', label: 'Agent decisions' },
  { view: 'evals', label: 'Evals' },
]

function NavLink({
  label,
  active,
  onClick,
}: {
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`relative cursor-pointer pb-1 text-sm font-semibold tracking-tight transition-colors ${
        active ? 'text-white' : 'text-white/70 hover:text-white'
      }`}
    >
      {label}
      {active && (
        <span className="absolute inset-x-0 -bottom-1 h-0.5 rounded-full bg-gold" aria-hidden />
      )}
    </button>
  )
}

export interface AppHeaderProps {
  currentView: AppView
  onNavigate: (view: AppView) => void
  pendingApprovals: number
  locationName?: string
  managerName?: string
  managerRole?: string
  onLogout?: () => void
}

/**
 * Dark House-Green header band per the user mockups: wordmark, text nav with
 * gold underline for the active view, operator group on the right and the
 * location name. The gold "Demo simulator" pill opens the demo simulator.
 */
export function AppHeader({
  currentView,
  onNavigate,
  pendingApprovals,
  locationName = 'La Terraza del Puerto',
  managerName,
  managerRole,
  onLogout,
}: AppHeaderProps): ReactNode {
  return (
    <header role="banner" className="bg-green-house text-white">
      <div className="mx-auto flex h-16 max-w-[1440px] flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 md:px-6">
        <div className="flex items-center gap-6">
          <button
            type="button"
            onClick={() => onNavigate('today')}
            className="cursor-pointer text-lg font-bold tracking-tight transition-opacity hover:opacity-80"
          >
            Shift Rescue
          </button>
          <nav aria-label="Principal" className="hidden items-center gap-5 md:flex">
            {MAIN_NAV.map((item) => (
              <NavLink
                key={item.view}
                label={item.label}
                active={currentView === item.view}
                onClick={() => onNavigate(item.view)}
              />
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-6">
          <nav aria-label="Operador" className="hidden items-center gap-5 lg:flex">
            {OPERATOR_NAV.map((item) => (
              <NavLink
                key={item.view}
                label={item.label}
                active={currentView === item.view}
                onClick={() => onNavigate(item.view)}
              />
            ))}
          </nav>
          {pendingApprovals > 0 && (
            <span className="flex size-5 items-center justify-center rounded-full bg-gold text-xs font-bold text-green-house">
              {pendingApprovals}
            </span>
          )}
          <span className="hidden text-sm tracking-tight text-white/80 md:block">
            {locationName}
          </span>
          <button
            type="button"
            onClick={() => onNavigate('simulator')}
            className="cursor-pointer rounded-pill bg-gold px-4 py-2 text-sm font-semibold tracking-tight text-green-house transition-all duration-200 ease-in-out hover:opacity-90 active:scale-95"
          >
            Demo simulator
          </button>
          {onLogout && (
            <div className="flex items-center gap-3 border-l border-white/20 pl-4">
              {managerName && (
                <span className="hidden text-sm tracking-tight text-white/80 xl:block">
                  {managerName}
                  {managerRole ? ` · ${managerRole}` : ''}
                </span>
              )}
              <button
                type="button"
                onClick={onLogout}
                className="cursor-pointer text-sm font-semibold tracking-tight text-white/80 transition-colors hover:text-white"
              >
                Log out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}

/**
 * Floating action button — the DESIGN.md "Frap" treatment.
 */
export function Fab({ label, onClick }: { label: string; onClick?: () => void }) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className="fixed bottom-6 right-6 z-20 flex size-14 cursor-pointer items-center justify-center rounded-full bg-green-accent text-white shadow-frap transition-transform duration-200 ease-in-out active:scale-95"
    >
      <svg viewBox="0 0 16 16" className="size-6 fill-white" aria-hidden="true">
        <path d="M7.25 2h1.5v5.25H14v1.5H8.75V14h-1.5V8.75H2v-1.5h5.25V2Z" />
      </svg>
    </button>
  )
}
