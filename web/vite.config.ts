/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  base: process.env.VITE_BASE_PATH ?? '/',
  plugins: [react(), tailwindcss()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: true,
    // The first test per file that cold-boots <App/> pays a one-time lazy
    // route-chunk compile/import cost that can exceed vitest's 5s default,
    // especially on a loaded machine -- every later test in the same file
    // (reusing already-compiled chunks) finishes in well under a second.
    // Not a runtime regression; just headroom for that one-time cost.
    testTimeout: 15000,
  },
})
