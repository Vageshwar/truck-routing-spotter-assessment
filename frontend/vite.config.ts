import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Serve maplibre-gl as is in dev. Pre-bundling moves it into .vite/deps,
  // where it can't find its worker file.
  optimizeDeps: { exclude: ['maplibre-gl'] },
  build: {
    // maplibre-gl alone is about 1 MB (290 kB gzipped) and already gets its own chunk
    chunkSizeWarningLimit: 1200,
  },
})
