import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const CSP = [
  "default-src 'self'",
  "script-src 'self' 'wasm-unsafe-eval'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https://*.basemaps.cartocdn.com https://*.cartocdn.com",
  "connect-src 'self' https://*.basemaps.cartocdn.com https://*.cartocdn.com",
  "font-src 'self' data:",
  "object-src 'none'",
  "base-uri 'self'",
  "frame-ancestors 'none'",
].join('; ')

const SECURITY_HEADERS = {
  'Content-Security-Policy':   CSP,
  'X-Content-Type-Options':    'nosniff',
  'X-Frame-Options':           'DENY',
  'Referrer-Policy':           'strict-origin-when-cross-origin',
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  base: mode === 'development' ? '/' : '/project-backbone/',
  build: {
    // Generate source maps in development only; omit in production builds
    // to avoid exposing implementation details publicly.
    sourcemap: mode === 'development',
  },
  preview: {
    headers: SECURITY_HEADERS,
  },
}))
