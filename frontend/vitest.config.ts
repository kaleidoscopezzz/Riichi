import { defineConfig } from 'vitest/config'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  test: {
    environment: 'node',
    clearMocks: true,
    setupFiles: ['src/test/setup-dom.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
  },
})
