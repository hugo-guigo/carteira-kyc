import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],  // e2e/ é do Playwright, que roda em outro job
    setupFiles: ['./src/testes/preparar.ts'],
  },
})
