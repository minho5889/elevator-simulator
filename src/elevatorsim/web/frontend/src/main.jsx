import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import ArenaApp from './ArenaApp.jsx'
import { ArenaProvider } from './state/arenaStore.jsx'
import { LanguageProvider } from './i18n.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <LanguageProvider>
      <ArenaProvider>
        <ArenaApp />
      </ArenaProvider>
    </LanguageProvider>
  </StrictMode>,
)
