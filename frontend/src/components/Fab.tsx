export interface FabProps {
  label: string
  onClick?: () => void
}

/**
 * Floating circular action button — the DESIGN.md "Frap" treatment:
 * Green Accent fill, layered shadow stack, scale(0.95) on press.
 */
export function Fab({ label, onClick }: FabProps) {
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
