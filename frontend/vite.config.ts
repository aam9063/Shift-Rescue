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
