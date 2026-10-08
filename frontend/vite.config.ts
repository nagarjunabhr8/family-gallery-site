import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // Backend (FastAPI) runs on :8765 during development
    proxy: {
      '/api': 'http://127.0.0.1:8765',
    },
  },
})
