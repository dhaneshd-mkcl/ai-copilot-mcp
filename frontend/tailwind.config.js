export default {
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
        display: ['Inter', 'sans-serif'],
      },
      colors: {
        'text-primary': '#0f172a',
        'text-secondary': '#475569',
        'border-dim': 'rgba(226, 232, 240, 0.4)',
        surface: {
          DEFAULT: '#ffffff',
          1: 'rgba(255, 255, 255, 0.9)',
          2: 'rgba(248, 250, 252, 0.8)',
          3: '#f1f5f9',
        },
        accent: {
          cyan: '#38bdf8',
          green: '#4ade80',
          orange: '#fbbf24',
          purple: '#c084fc',
          pink: '#f472b6',
        },
        'border': '#e2e8f0',
      },
      boxShadow: {
        'glow-cyan': '0 0 20px rgba(56, 189, 248, 0.3)',
        'glow-purple': '0 0 20px rgba(192, 132, 252, 0.3)',
        'premium': '0 10px 40px -10px rgba(0, 0, 0, 0.08), 0 5px 15px -3px rgba(0, 0, 0, 0.04)',
      },
      animation: {
        'pulse-slow': 'pulse 3s ease-in-out infinite',
        'fade-in': 'fadeIn 0.5s cubic-bezier(0.16, 1, 0.3, 1)',
        'slide-up': 'slideUp 0.5s cubic-bezier(0.16, 1, 0.3, 1)',
        'gradient': 'gradient 6s ease infinite',
        'float': 'float 3s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: { from: { opacity: 0 }, to: { opacity: 1 } },
        slideUp: { from: { opacity: 0, transform: 'translateY(12px)' }, to: { opacity: 1, transform: 'translateY(0)' } },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-10px)' },
        },
        gradient: {
          '0%': { 'background-position': '0% 50%' },
          '50%': { 'background-position': '100% 50%' },
          '100%': { 'background-position': '0% 50%' },
        }
      }
    }
  },
  plugins: []
}
