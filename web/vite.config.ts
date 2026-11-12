import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev: proxy /api to the local S6 server so the browser sees one origin.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': { target: process.env.NOTCH_API ?? 'http://127.0.0.1:8000', changeOrigin: true } },
  },
})
