import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    tailwindcss(),
  ],
  server: {
    port: 9081,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:9091',
        changeOrigin: true,
      },
    },
  },
  preview: {
    port: 9081,
    host: true,
  },
})
