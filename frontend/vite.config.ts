import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    // The single app bundle (React, Motion, GSAP) is ~575 kB, ~185 kB gzipped.
    chunkSizeWarningLimit: 800,
  },
  server: {
    proxy: {
      // FastAPI backend (backend/) runs on :8000 during development
      '/api': 'http://localhost:8000',
    },
  },
})
