/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './accounts/**/*.py',
    './banking/**/*.py',
    './categories/**/*.py',
    './core/**/*.py',
    './dashboard/**/*.py',
    './investments/**/*.py',
    './pages/**/*.py',
    './transactions/**/*.py',
    './static/js/**/*.js',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        cream: { DEFAULT: '#FAF8F3', dark: '#EBE7DE' },
        forest: { DEFAULT: '#1A2E26', light: '#2A4338', deep: '#101E18' },
        caramel: { DEFAULT: '#B88A59', light: '#D4AD86', ink: '#8A5A2F' },
        income: { DEFAULT: '#176B52', light: '#64D8B1' },
        expense: { DEFAULT: '#B42318', light: '#FF8A80' },
        investment: { DEFAULT: '#7C5C13', light: '#F4C95D' },
        installment: { DEFAULT: '#6B4E8A', light: '#C4A7E7' },
        fixed: { DEFAULT: '#A65300', light: '#FFB45C' },
        oneoff: { DEFAULT: '#52605A', light: '#B8C0BC' },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
    },
  },
};
