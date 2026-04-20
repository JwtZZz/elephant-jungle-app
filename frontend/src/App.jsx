import { useState } from 'react'
import Sidebar from './components/Sidebar'
import WorkspacePanel from './components/WorkspacePanel'
import ThemeToggle from './components/ThemeToggle'
import ChatPanel from './components/ChatPanel'
import { useTheme } from './hooks/useTheme'
import { useMarketData } from './hooks/useMarketData'

export default function App() {
  const [activeView, setActiveView] = useState('markets')
  const { theme, setTheme } = useTheme()
  const { apiBase, marketRows, briefs } = useMarketData()

  return (
    <div className="layout">
      <div className="main">
        <div className="workspace-shell">
          <Sidebar activeView={activeView} onSelect={setActiveView} />
          <WorkspacePanel activeView={activeView} marketRows={marketRows} briefs={briefs} />
        </div>
      </div>
      <ThemeToggle theme={theme} setTheme={setTheme} />
      <ChatPanel apiBase={apiBase} theme={theme} />
    </div>
  )
}
