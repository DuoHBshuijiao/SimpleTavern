import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

const parsedPort = Number(process.env.SIMPLETAVERN_FRONTEND_PORT)
const frontendPort = Number.isFinite(parsedPort) && parsedPort > 0 ? parsedPort : 9081
const apiProxy = process.env.SIMPLETAVERN_API_PROXY?.trim() || 'http://127.0.0.1:9091'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    tailwindcss(),
  ],
  server: {
    port: frontendPort,
    proxy: {
      '/api': {
        target: apiProxy,
        changeOrigin: true,
      },
    },
  },
  preview: {
    port: frontendPort,
    host: true,
  },
})
