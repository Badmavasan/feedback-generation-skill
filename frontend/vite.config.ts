import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  base: '/feedback-generation/',
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/feedback-generation/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/feedback-generation\/api/, ''),
      },
    },
  },
})
