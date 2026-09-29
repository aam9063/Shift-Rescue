/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // Dev only: forward /api to the local backend so the SPA needs no CORS
      // in development (same as the deployed Caddy setup).
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // The demo-only routes live under /dev (spec §7.5). Without this the SPA
      // fallback answers HTML and the simulator's clock reads undefined.
      '/dev': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // Live dashboard channel (spec §7.5): a WebSocket needs the upgrade
      // forwarded too, or the handshake never completes and the dashboard shows
      // "connecting" forever.
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globals: false,
    // Tests run hermetically: the data-source seam selects the mock fixture
    // instead of the API-backed implementation (no network).
    env: {
      VITE_USE_MOCK: 'true',
    },
  },
})
