import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// 開發時把 /api 轉給本機後端；正式環境由 Caddy 轉發。
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
