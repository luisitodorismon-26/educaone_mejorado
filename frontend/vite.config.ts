import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// v2.13.23: el backend corre en el puerto 8080.
// TODAS las llamadas /api pasan por este proxy. El frontend NO tiene
// ningún puerto hardcodeado (ver src/services/api.ts), así que este es
// el ÚNICO lugar donde se define el puerto del backend.
const BACKEND_PORT = 8080

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: `http://localhost:${BACKEND_PORT}`,
        changeOrigin: true,
      }
    }
  }
})
