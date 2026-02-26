import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          bg:      '#050203',
          surface: '#0c0706',
          walnut:  '#443324',
          gold:    '#ECCB4C',
          white:   '#FEFEFE',
          muted:   '#9e8c7a',
        },
      },
      fontFamily: {
        sans: ['Hanken Grotesk', 'system-ui', 'arial', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      backgroundImage: {
        'grid-pattern': `
          linear-gradient(rgba(68,51,36,0.15) 1px, transparent 1px),
          linear-gradient(90deg, rgba(68,51,36,0.15) 1px, transparent 1px)
        `,
      },
      backgroundSize: {
        'grid': '40px 40px',
      },
      keyframes: {
        'accordion-down': { from: { height: '0' }, to: { height: 'var(--radix-accordion-content-height)' } },
        'accordion-up':   { from: { height: 'var(--radix-accordion-content-height)' }, to: { height: '0' } },
        'fade-in':        { from: { opacity: '0' }, to: { opacity: '1' } },
        'fade-out':       { from: { opacity: '1' }, to: { opacity: '0' } },
        'zoom-in-95':     { from: { opacity: '0', transform: 'scale(0.95)' }, to: { opacity: '1', transform: 'scale(1)' } },
        'zoom-out-95':    { from: { opacity: '1', transform: 'scale(1)' }, to: { opacity: '0', transform: 'scale(0.95)' } },
        'slide-in-from-right': { from: { transform: 'translateX(100%)' }, to: { transform: 'translateX(0)' } },
        'slide-out-to-right':  { from: { transform: 'translateX(0)' }, to: { transform: 'translateX(100%)' } },
        'slide-in-from-left':  { from: { transform: 'translateX(-100%)' }, to: { transform: 'translateX(0)' } },
        'slide-out-to-left':   { from: { transform: 'translateX(0)' }, to: { transform: 'translateX(-100%)' } },
        'slide-in-from-top':    { from: { transform: 'translateY(-100%)' }, to: { transform: 'translateY(0)' } },
        'slide-out-to-top':     { from: { transform: 'translateY(0)' }, to: { transform: 'translateY(-100%)' } },
        'slide-in-from-bottom': { from: { transform: 'translateY(100%)' }, to: { transform: 'translateY(0)' } },
        'slide-out-to-bottom':  { from: { transform: 'translateY(0)' }, to: { transform: 'translateY(100%)' } },
        'slide-in-from-top-2':    { from: { transform: 'translateY(-0.5rem)', opacity: '0' }, to: { transform: 'translateY(0)', opacity: '1' } },
        'slide-in-from-bottom-2': { from: { transform: 'translateY(0.5rem)', opacity: '0' }, to: { transform: 'translateY(0)', opacity: '1' } },
        'slide-in-from-left-2':   { from: { transform: 'translateX(-0.5rem)', opacity: '0' }, to: { transform: 'translateX(0)', opacity: '1' } },
        'slide-in-from-right-2':  { from: { transform: 'translateX(0.5rem)', opacity: '0' }, to: { transform: 'translateX(0)', opacity: '1' } },
      },
      animation: {
        'pulse-dot':             'pulse 1.5s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'accordion-down':        'accordion-down 0.2s ease-out',
        'accordion-up':          'accordion-up 0.2s ease-out',
        'fade-in-0':             'fade-in 0.15s ease-out',
        'fade-out-0':            'fade-out 0.15s ease-in',
        'zoom-in-95':            'zoom-in-95 0.15s ease-out',
        'zoom-out-95':           'zoom-out-95 0.15s ease-in',
        'slide-in-from-right':   'slide-in-from-right 0.3s ease-out',
        'slide-out-to-right':    'slide-out-to-right 0.3s ease-in',
        'slide-in-from-left':    'slide-in-from-left 0.3s ease-out',
        'slide-out-to-left':     'slide-out-to-left 0.3s ease-in',
        'slide-in-from-top':     'slide-in-from-top 0.3s ease-out',
        'slide-out-to-top':      'slide-out-to-top 0.3s ease-in',
        'slide-in-from-bottom':  'slide-in-from-bottom 0.3s ease-out',
        'slide-out-to-bottom':   'slide-out-to-bottom 0.3s ease-in',
        'slide-in-from-top-2':    'slide-in-from-top-2 0.15s ease-out',
        'slide-in-from-bottom-2': 'slide-in-from-bottom-2 0.15s ease-out',
        'slide-in-from-left-2':   'slide-in-from-left-2 0.15s ease-out',
        'slide-in-from-right-2':  'slide-in-from-right-2 0.15s ease-out',
      },
    },
  },
  plugins: [],
}

export default config
