/** @type {import('tailwindcss').Config} */
// path = จาก <APP>/.app/shell/tailwind.config.js ขึ้นไปถึง Mega Project root → .shared/
//   .app/shell/ → ..  ขึ้นไป .app/
//   .app/       → ..  ขึ้นไป <APP>/
//   <APP>/      → ..  ขึ้นไป Mega Project/
// ถ้า structure ของแอปต่างจากนี้ ปรับจำนวน ../ ให้ตรง
let inkTokens
try {
  inkTokens = require('../../../.shared/tailwind/tokens.cjs')
} catch {
  inkTokens = {
    themeExtend: {
      colors: {
        vscode: {
          bg: '#1e1e1e',
          editor: '#252526',
          panel: '#2d2d30',
          border: '#3e3e42',
          fg: '#cccccc',
          muted: '#858585',
          input: '#3c3c3c',
          focus: '#007acc',
        },
      },
      borderRadius: {
        'mac-sm': '6px',
      },
      boxShadow: {
        mac: '0 18px 50px rgba(0, 0, 0, 0.32)',
      },
    },
  }
}

module.exports = {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: inkTokens.themeExtend,
  },
  darkMode: 'class',
  plugins: [],
}
