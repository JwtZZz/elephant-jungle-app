import { useEffect, useState } from 'react'
import Sidebar from './components/Sidebar'
import WorkspacePanel from './components/WorkspacePanel'
import ThemeToggle from './components/ThemeToggle'
import ChatPanel from './components/ChatPanel'
import { useTheme } from './hooks/useTheme'
import { useMarketData } from './hooks/useMarketData'

export default function App() {
  const [activeView, setActiveView] = useState('markets')
  const [language, setLanguage] = useState(() => window.localStorage.getItem('ej-language') || 'en')
  const { theme, setTheme } = useTheme()
  const { apiBase, marketRows, briefs } = useMarketData()

  useEffect(() => {
    window.localStorage.setItem('ej-language', language)
  }, [language])

  return (
    <div className="layout">
      <div className="main">
        <div className="workspace-shell">
          <Sidebar activeView={activeView} onSelect={setActiveView} language={language} />
          <WorkspacePanel activeView={activeView} apiBase={apiBase} marketRows={marketRows} briefs={briefs} language={language} setLanguage={setLanguage} />
        </div>
      </div>
      <div className="right-col">
        <div className="right-topbar">
          <ThemeToggle theme={theme} setTheme={setTheme} language={language} />
        </div>
        <ChatPanel apiBase={apiBase} language={language} />
      </div>
    </div>
  )
}
