import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // same-origin in dev: the browser only ever talks to :5173, so session
    // cookies flow without any CORS setup. In prod the backend serves the
    // built SPA from the same origin and no proxy exists.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
