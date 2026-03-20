import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  base: '/',
  build: {
    // Generate source maps in development only; omit in production builds
    // to avoid exposing implementation details publicly.
    sourcemap: mode === 'development',
  },
}))
