import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

// Read from disk: the Tailwind Vite plugin intercepts CSS module imports,
// so ?raw returns an empty string under vitest.
const tokens = readFileSync(resolve(process.cwd(), 'src/design/tokens.css'), 'utf8')

/**
 * Contract tests for the design tokens defined in DESIGN.md (Starbucks-inspired
 * design system). These lock the exact values so screens can rely on them.
 */
function assertToken(css: string, name: string, value: string): void {
  // value is the literal token value; escape it once for use in a RegExp.
  const pattern = new RegExp(`--${name}\\s*:\\s*${value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*;`)
  expect(css, `expected token --${name} to equal ${value}`).toMatch(pattern)
}

describe('design tokens (DESIGN.md)', () => {
  it('defines the four-tier green system with exact brand values', () => {
    assertToken(tokens, 'color-green-starbucks', '#006241')
    assertToken(tokens, 'color-green-accent', '#00754A')
    assertToken(tokens, 'color-green-house', '#1E3932')
    assertToken(tokens, 'color-green-uplift', '#2b5148')
    assertToken(tokens, 'color-green-light', '#d4e9e2')
  })

  it('defines the warm neutral canvas and card surfaces', () => {
    assertToken(tokens, 'color-canvas', '#f2f0eb')
    assertToken(tokens, 'color-ceramic', '#edebe9')
    assertToken(tokens, 'color-surface', '#ffffff')
    assertToken(tokens, 'color-neutral-cool', '#f9f9f9')
  })

  it('reserves gold for status ceremony and defines semantic states', () => {
    assertToken(tokens, 'color-gold', '#cba258')
    assertToken(tokens, 'color-gold-light', '#dfc49d')
    assertToken(tokens, 'color-gold-lightest', '#faf6ee')
    assertToken(tokens, 'color-error', '#c82014')
    assertToken(tokens, 'color-warning', '#fbbc05')
  })

  it('defines text colors that never use pure black', () => {
    assertToken(tokens, 'color-text-primary', 'rgba(0, 0, 0, 0.87)')
    assertToken(tokens, 'color-text-secondary', 'rgba(0, 0, 0, 0.58)')
    assertToken(tokens, 'color-text-on-dark', 'rgba(255, 255, 255, 1)')
    assertToken(tokens, 'color-text-on-dark-soft', 'rgba(255, 255, 255, 0.7)')
  })

  it('defines the border radius scale (12px cards, 50px pill buttons)', () => {
    assertToken(tokens, 'radius-card', '12px')
    assertToken(tokens, 'radius-pill', '50px')
  })

  it('defines the rem-based spacing scale anchored at 1.6rem', () => {
    assertToken(tokens, 'space-1', '0.4rem')
    assertToken(tokens, 'space-2', '0.8rem')
    assertToken(tokens, 'space-3', '1.6rem')
    assertToken(tokens, 'space-4', '2.4rem')
    assertToken(tokens, 'space-5', '3.2rem')
    assertToken(tokens, 'space-6', '4rem')
  })

  it('defines layered whisper-soft shadow stacks, not heavy drop shadows', () => {
    assertToken(
      tokens,
      'shadow-card',
      '0 0 0.5px rgba(0, 0, 0, 0.14), 0 1px 1px rgba(0, 0, 0, 0.24)',
    )
    assertToken(
      tokens,
      'shadow-nav',
      '0 1px 3px rgba(0, 0, 0, 0.1), 0 2px 2px rgba(0, 0, 0, 0.06), 0 0 2px rgba(0, 0, 0, 0.07)',
    )
  })

  it('sets Inter as the font substitute for the proprietary SoDoSans', () => {
    assertToken(
      tokens,
      'font-sans',
      'Inter, "Helvetica Neue", Helvetica, Arial, sans-serif',
    )
  })
})
