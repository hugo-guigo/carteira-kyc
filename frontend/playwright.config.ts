import { defineConfig } from '@playwright/test'
import { existsSync } from 'node:fs'
import { resolve } from 'node:path'

// Localmente lê DEMO_SENHA e o banco do .env da raiz; no CI as variáveis vêm do workflow.
if (existsSync('../.env')) process.loadEnvFile('../.env')

const python = process.env.PYTHON ?? resolve('../backend/.venv/Scripts/python.exe')
const manage = resolve('../backend/manage.py')

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  use: {
    baseURL: 'http://127.0.0.1:5173',
    // Local: usa o Edge instalado, sem baixar navegador. CI: Chromium do Playwright.
    channel: process.env.CI ? undefined : 'msedge',
    viewport: { width: 1100, height: 760 },
  },
  webServer: [
    {
      command: `"${python}" "${manage}" runserver 127.0.0.1:8000 --noreload`,
      url: 'http://127.0.0.1:8000/api/saude',
      reuseExistingServer: !process.env.CI,
    },
    {
      command: 'npx vite --host 127.0.0.1 --port 5173 --strictPort',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: !process.env.CI,
    },
  ],
})
