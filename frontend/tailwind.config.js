/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        unified: {
          red: '#C8102E',
          gold: '#F5A623',
          dark: '#1A1A2E',
          gray: '#F5F5F5',
        },
      },
    },
  },
  plugins: [],
}
