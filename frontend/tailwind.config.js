/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['Space Grotesk', 'sans-serif'],
        body: ['IBM Plex Sans', 'sans-serif'],
      },
      colors: {
        low: '#0f9d58',
        medium: '#f6c343',
        high: '#d93025',
      },
      boxShadow: {
        panel: '0 20px 50px -22px rgba(11, 38, 56, 0.45)',
      },
      keyframes: {
        pulseRing: {
          '0%': { transform: 'scale(0.85)', opacity: '0.85' },
          '70%': { transform: 'scale(1.1)', opacity: '0.15' },
          '100%': { transform: 'scale(1.1)', opacity: '0' },
        },
      },
      animation: {
        pulseRing: 'pulseRing 1.1s ease-out infinite',
      },
    },
  },
  plugins: [],
};
