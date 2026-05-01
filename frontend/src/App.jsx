import { useEffect, useState } from 'react'
import Sidebar from './components/Sidebar'
import WorkspacePanel from './components/WorkspacePanel'
import ChatPanel from './components/ChatPanel'
import { useMarketData } from './hooks/useMarketData'

export default function App() {
  const [activeView, setActiveView] = useState('markets')
  const [language, setLanguage] = useState(() => window.localStorage.getItem('ej-language') || 'en')
  const [isMobileChatOnly, setIsMobileChatOnly] = useState(() => {
    if (typeof window === 'undefined') return false
    return window.matchMedia('(max-width: 760px)').matches
  })
  const { apiBase, marketRows, briefs } = useMarketData()

  useEffect(() => {
    window.localStorage.setItem('ej-language', language)
  }, [language])

  useEffect(() => {
    if (typeof window === 'undefined') return undefined

    const mediaQuery = window.matchMedia('(max-width: 760px)')
    const syncMobileState = (event) => {
      setIsMobileChatOnly(event.matches)
    }

    setIsMobileChatOnly(mediaQuery.matches)
    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', syncMobileState)
      return () => mediaQuery.removeEventListener('change', syncMobileState)
    }

    mediaQuery.addListener(syncMobileState)
    return () => mediaQuery.removeListener(syncMobileState)
  }, [])

  return (
    <div className={`layout ${isMobileChatOnly ? 'mobile-chat-only' : ''}`}>
      {!isMobileChatOnly ? (
        <div className="main">
          <div className="workspace-shell">
            <Sidebar activeView={activeView} onSelect={setActiveView} language={language} />
            <WorkspacePanel activeView={activeView} apiBase={apiBase} marketRows={marketRows} briefs={briefs} language={language} setLanguage={setLanguage} />
          </div>
        </div>
      ) : null}
      <ChatPanel apiBase={apiBase} language={language} setLanguage={setLanguage} mobileOnly={isMobileChatOnly} />
    </div>
  )
}
