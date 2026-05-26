/** @type {import('tailwindcss').Config} */
// path = จาก <APP>/.app/shell/tailwind.config.js ขึ้นไปถึง Mega Project root → .shared/
//   .app/shell/ → ..  ขึ้นไป .app/
//   .app/       → ..  ขึ้นไป <APP>/
//   <APP>/      → ..  ขึ้นไป Mega Project/
// ถ้า structure ของแอปต่างจากนี้ ปรับจำนวน ../ ให้ตรง
const inkTokens = require('../../../.shared/tailwind/tokens.cjs')

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
