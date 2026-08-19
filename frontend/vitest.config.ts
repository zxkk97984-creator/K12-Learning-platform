import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vitest/config'

export default defineConfig({
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
    // 强制 NODE_ENV=test：shell 若为 production，React 会走 production 构建（无 React.act），
    // 导致 @testing-library/react 渲染失败
    env: { NODE_ENV: 'test' },
  },
})
