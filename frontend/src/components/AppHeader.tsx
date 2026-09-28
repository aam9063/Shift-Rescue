import { useEffect, useState, type ReactNode } from 'react'

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

/**
 * Drawer item: the same gold active indicator as the desktop nav, on the same
 * dark band, with a 44px touch target (DESIGN.md §8) and a gold focus ring
 * that stays visible on House Green.
 */
function DrawerLink({
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
      className={`relative flex min-h-11 w-full cursor-pointer items-center text-left text-sm font-semibold tracking-tight transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold ${
        active ? 'text-white' : 'text-white/70 hover:text-white'
      }`}
    >
      {label}
      {active && (
        <span className="absolute bottom-1 left-0 h-0.5 w-10 rounded-full bg-gold" aria-hidden />
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
 *
 * Responsive contract (DESIGN.md §8): below the tablet breakpoint the two
 * desktop navs are hidden, so an `lg:hidden` hamburger opens a drawer listing
 * every destination from both groups. CSS-controlled siblings — no JS media
 * queries: the hamburger is `lg:hidden` (it must survive the tablet range,
 * where the main nav is visible but the operator group is not) and the navs keep their
 * `hidden md:flex` / `hidden lg:flex` classes.
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
  const [menuOpen, setMenuOpen] = useState(false)

  // Escape closes the drawer no matter where the focus sits.
  useEffect(() => {
    if (!menuOpen) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMenuOpen(false)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [menuOpen])

  const navigateFromDrawer = (view: AppView) => {
    setMenuOpen(false)
    onNavigate(view)
  }

  return (
    <header role="banner" className="bg-green-house text-white">
      <div className="mx-auto flex min-h-16 max-w-[1440px] flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-2 md:px-6">
        <div className="flex items-center gap-3 md:gap-6">
          <button
            type="button"
            onClick={() => onNavigate('today')}
            className="pointer-coarse:min-h-11 cursor-pointer text-lg font-bold tracking-tight transition-opacity hover:opacity-80"
          >
            Shift Rescue
          </button>
          <button
            type="button"
            aria-expanded={menuOpen}
            aria-controls="mobile-nav-panel"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            onClick={() => setMenuOpen((open) => !open)}
            className="flex size-11 cursor-pointer items-center justify-center rounded-md text-white transition-colors hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold lg:hidden"
          >
            <svg viewBox="0 0 16 16" className="size-5 fill-current" aria-hidden="true">
              {menuOpen ? (
                <path d="M3.4 2.34 8 6.94l4.6-4.6 1.06 1.06L9.06 8l4.6 4.6-1.06 1.06L8 9.06l-4.6 4.6-1.06-1.06L6.94 8l-4.6-4.6L3.4 2.34Z" />
              ) : (
                <path d="M1 3h14v1.5H1V3Zm0 4.25h14v1.5H1v-1.5ZM1 11.5h14V13H1v-1.5Z" />
              )}
            </svg>
          </button>
          <nav aria-label="Main" className="hidden items-center gap-5 md:flex">
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
        <div className="flex items-center gap-3 md:gap-6">
          <nav aria-label="Operator" className="hidden items-center gap-5 lg:flex">
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
            className="pointer-coarse:min-h-11 cursor-pointer rounded-pill bg-gold px-4 py-2 text-sm font-semibold tracking-tight text-green-house transition-all duration-200 ease-in-out hover:opacity-90 active:scale-95"
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
                className="pointer-coarse:min-h-11 cursor-pointer text-sm font-semibold tracking-tight text-white/80 transition-colors hover:text-white"
              >
                Log out
              </button>
            </div>
          )}
        </div>
        {menuOpen && (
          <div id="mobile-nav-panel" className="order-last w-full basis-full lg:hidden">
            <nav aria-label="Menu" className="border-t border-white/15 pb-2 pt-1">
              <p className="px-1 pb-1 pt-2 text-xs font-semibold uppercase tracking-wider text-white/50">
                Main
              </p>
              {MAIN_NAV.map((item) => (
                <DrawerLink
                  key={item.view}
                  label={item.label}
                  active={currentView === item.view}
                  onClick={() => navigateFromDrawer(item.view)}
                />
              ))}
              <p className="px-1 pb-1 pt-3 text-xs font-semibold uppercase tracking-wider text-white/50">
                Operator
              </p>
              {OPERATOR_NAV.map((item) => (
                <DrawerLink
                  key={item.view}
                  label={item.label}
                  active={currentView === item.view}
                  onClick={() => navigateFromDrawer(item.view)}
                />
              ))}
              {onLogout && (
                <div className="mt-2 flex min-h-11 items-center justify-between gap-3 border-t border-white/15 pt-2">
                  <span className="truncate text-sm tracking-tight text-white/80">
                    {managerName}
                    {managerRole ? ` · ${managerRole}` : ''}
                  </span>
                  <button
                    type="button"
                    onClick={onLogout}
                    className="min-h-11 shrink-0 cursor-pointer px-1 text-sm font-semibold tracking-tight text-white/80 transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
                  >
                    Log out
                  </button>
                </div>
              )}
            </nav>
          </div>
        )}
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
