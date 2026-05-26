import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { useStore } from './state/store'
import { detectChapterNumber, naturalCompare, splitStemTrailingDigits } from './lib/chapters'
import '@vscode/codicons/dist/codicon.css'
import './index.css'

// Test hooks — used by Playwright E2E specs in e2e/. Safe to leave on in
// production builds since the harness is local-only and reading store state
// isn't a security boundary.
;(window as unknown as { __inkcopyStoreForTests: typeof useStore }).__inkcopyStoreForTests = useStore
;(window as unknown as { __inkcopyChaptersForTests: object }).__inkcopyChaptersForTests = {
  detectChapterNumber,
  naturalCompare,
  splitStemTrailingDigits,
}

const root = document.getElementById('root')!
createRoot(root).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
