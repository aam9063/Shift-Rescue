import { useState } from 'react'
import { useSettings } from '../services/dashboard'

const LEVEL_LABEL: Record<string, string> = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
}

/**
 * Settings screen (spec §7.6 screen 5, mockup "Ajustes"): pause-the-agent
 * toggle, ranking weight sliders, waves and quiet hours.
 */
export function SettingsScreen() {
  const { settings, save, saved } = useSettings()
  const [draft, setDraft] = useState(settings)
  // React's "adjust state when a prop changes" pattern. With live data the
  // server values arrive after the first paint, so the draft follows the
  // query data identity — never clobbering in-progress edits while a save is
  // in flight (and a failed save keeps the operator's draft for retrying).
  const [draftedFrom, setDraftedFrom] = useState(settings)
  const [savePending, setSavePending] = useState(false)

  if (settings !== draftedFrom && !savePending) {
    setDraftedFrom(settings)
    setDraft(settings)
  }
  if (saved && savePending) {
    setSavePending(false)
  }

  const handleSave = () => {
    setSavePending(true)
    save(draft)
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <h1 className="font-serif text-4xl font-semibold tracking-tight text-green-starbucks">
        Settings for La Terraza del Puerto
      </h1>

      <div
        className={`rounded-card bg-surface p-5 shadow-card ${
          draft.agentPaused ? 'border-2 border-error' : 'border border-black/5'
        }`}
      >
        <div className="flex items-center justify-between">
          <div>
            <p className="text-base font-semibold tracking-tight">Pausar agente</p>
            <p className="text-sm tracking-tight text-text-secondary">
              New absences will be forwarded directly to the manager.
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={draft.agentPaused}
            aria-label="Pausar agente"
            onClick={() => setDraft({ ...draft, agentPaused: !draft.agentPaused })}
            className={`relative h-7 w-12 cursor-pointer rounded-full transition-colors after:absolute after:-inset-2.5 after:content-[''] ${
              draft.agentPaused ? 'bg-error' : 'bg-black/15'
            }`}
          >
            <span
              className={`absolute top-1 size-5 rounded-full bg-white transition-all ${
                draft.agentPaused ? 'left-6' : 'left-1'
              }`}
            />
          </button>
        </div>
      </div>

      <div className="rounded-card bg-surface p-5 shadow-card">
        <h2 className="mb-4 text-lg font-semibold tracking-tight">Candidate ranking weights</h2>
        <div className="space-y-4">
          {draft.rankingWeights.map((weight: { label: string; level: string }, index: number) => (
            <div key={weight.label}>
              <div className="flex justify-between text-sm tracking-tight">
                <span>{weight.label}</span>
                <span className="text-text-secondary">{LEVEL_LABEL[weight.level]}</span>
              </div>
              <button
                type="button"
                aria-label={`Weight: ${weight.label}`}
                onClick={() => {
                  const next = [...draft.rankingWeights]
                  next[index] = {
                    ...weight,
                    level: weight.level === 'high' ? 'medium' : 'high',
                  }
                  setDraft({ ...draft, rankingWeights: next })
                }}
                className="relative mt-1 h-1.5 w-full cursor-pointer rounded-full bg-green-accent after:absolute after:-inset-[19px] after:content-['']"
              />
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-card bg-surface p-5 shadow-card">
        <h2 className="mb-4 text-lg font-semibold tracking-tight">Waves</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <label className="block text-sm tracking-tight text-text-secondary">
            Candidates per wave
            <input
              type="number"
              min={1}
              max={10}
              value={draft.waveSize}
              onChange={(event) =>
                setDraft({ ...draft, waveSize: Number(event.target.value) })
              }
              className="mt-1 w-full rounded-card border border-input-border px-3 py-2 text-base text-text-primary"
            />
          </label>
          <label className="block text-sm tracking-tight text-text-secondary">
            Minutes between waves
            <input
              type="number"
              min={1}
              max={60}
              value={draft.waveIntervalMinutes}
              onChange={(event) =>
                setDraft({ ...draft, waveIntervalMinutes: Number(event.target.value) })
              }
              className="mt-1 w-full rounded-card border border-input-border px-3 py-2 text-base text-text-primary"
            />
          </label>
        </div>
      </div>

      <div className="rounded-card bg-surface p-5 shadow-card">
        <h2 className="mb-4 text-lg font-semibold tracking-tight">Quiet hours</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <label className="block text-sm tracking-tight text-text-secondary">
            From
            <input
              type="time"
              value={draft.quietStart}
              onChange={(event) => setDraft({ ...draft, quietStart: event.target.value })}
              className="mt-1 w-full rounded-card border border-input-border px-3 py-2 text-base text-text-primary"
            />
          </label>
          <label className="block text-sm tracking-tight text-text-secondary">
            To
            <input
              type="time"
              value={draft.quietEnd}
              onChange={(event) => setDraft({ ...draft, quietEnd: event.target.value })}
              className="mt-1 w-full rounded-card border border-input-border px-3 py-2 text-base text-text-primary"
            />
          </label>
        </div>
      </div>

      <button
        type="button"
        onClick={handleSave}
        className="pointer-coarse:min-h-11 cursor-pointer rounded-pill bg-green-accent px-6 py-3 text-sm font-semibold tracking-tight text-white transition-all duration-200 active:scale-95"
      >
        Save changes
      </button>
      {saved && (
        <p role="status" className="text-sm font-medium text-green-accent">
          Changes saved
        </p>
      )}
    </div>
  )
}
