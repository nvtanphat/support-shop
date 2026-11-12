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
        card: '0 10px 32px -12px rgba(109, 40, 217, 0.18), 0 2px 6px -2px rgba(109, 40, 217, 0.08)',
        chip: '0 4px 14px -6px rgba(109, 40, 217, 0.28)',
        cta: '0 12px 24px -8px rgba(76, 29, 149, 0.65)',
        pill: '0 4px 16px -4px rgba(109, 40, 217, 0.38), 0 0 0 1px rgba(124, 58, 237, 0.14)',
      },
      colors: {
        brand: {
          50: '#faf5ff',
          100: '#f3e8ff',
          200: '#e9d5ff',
          300: '#d8b4fe',
          400: '#c084fc',
          500: '#9333ea',
          600: '#7c3aed',
          700: '#6d28d9',
          800: '#5b21b6',
          900: '#4c1d95',
        },
        slate: {
          850: '#172033',
        }
      },
    },
  },
  plugins: [],
}
