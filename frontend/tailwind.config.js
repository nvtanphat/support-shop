/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Be Vietnam Pro"', 'Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        card: '0 10px 32px -12px rgba(16, 24, 22, 0.18), 0 2px 6px -2px rgba(16, 24, 22, 0.08)',
        chip: '0 4px 14px -6px rgba(16, 24, 22, 0.28)',
        cta: '0 12px 24px -8px rgba(16, 24, 22, 0.65)',
        pill: '0 4px 16px -4px rgba(16, 24, 22, 0.38), 0 0 0 1px rgba(16, 24, 22, 0.14)',
      },
      colors: {
        brand: {
          50: '#f0f7f5',
          100: '#e3f1ee',
          200: '#c3e2db',
          300: '#94cbbf',
          400: '#5aa99b',
          500: '#14897d',
          600: '#0f766e',
          700: '#115e59',
          800: '#134e4a',
          900: '#0f3b38',
        },
        slate: {
          850: '#172033',
        }
      },
    },
  },
  plugins: [],
}
