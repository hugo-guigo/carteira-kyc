import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// No GitHub Pages o site fica em /carteira-kyc/; localmente, na raiz.
export default defineConfig({
  base: process.env.BASE_PATH ?? '/',
  plugins: [react()],
})
