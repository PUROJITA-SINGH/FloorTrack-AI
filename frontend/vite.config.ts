import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api/assets': {
        target: 'http://localhost:8000',
        rewrite: (path) => path.replace(/^\/api\/assets/, '/api/v1/assets'),
      },
      '/api/zones': {
        target: 'http://localhost:8000',
        rewrite: (path) => path.replace(/^\/api\/zones/, '/api/v1/zones'),
      },
      '/api/inventory': {
        target: 'http://localhost:8000',
        rewrite: (path) => path.replace(/^\/api\/inventory/, '/api/v1/inventory'),
      },
      '/api/alerts': {
        target: 'http://localhost:8000',
        rewrite: (path) => path.replace(/^\/api\/alerts/, '/api/v1/alerts'),
      },
      '/api': 'http://localhost:8000',
    },
  },
})
