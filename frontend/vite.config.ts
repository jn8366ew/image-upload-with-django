/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // same-origin 세션 인증: /api는 Django runserver로 넘깁니다 (ADR-007)
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    coverage: {
      provider: 'v8',
      // TDD 대상 도메인 로직 (ADR-010)
      include: ['src/upload/**'],
      reporter: ['text', 'lcov', 'cobertura'],
    },
  },
})
