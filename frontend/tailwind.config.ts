import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './index.html',
    './src/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'ui-monospace', 'monospace'],
        serif: ['Georgia', 'Cambria', 'ui-serif', 'serif'],
      },
    },
  },
  plugins: [],
}

export default config
