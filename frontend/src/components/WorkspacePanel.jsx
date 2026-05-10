import { useEffect, useRef, useState } from 'react'
import MarketsView from './MarketsView'
import AgentsView, { warmTrendingCache } from './AgentsView'
import WalletView from './WalletView'
import SettingsView from './SettingsView'
import { useSpriteOrbit } from '../hooks/useSpriteOrbit'

function EmptyView() {
  return <div className="workspace-empty" aria-hidden="true" />
}

export default function WorkspacePanel({ activeView, apiBase, marketRows, briefs, language, setLanguage }) {
  const workspaceSpriteTrackRef = useRef(null)
  const workspaceSpriteShellRef = useRef(null)
  const [didVisitAgents, setDidVisitAgents] = useState(activeView === 'agents')
  const { spriteMode } = useSpriteOrbit([
    { trackRef: workspaceSpriteTrackRef, shellRef: workspaceSpriteShellRef, direction: -1 },
  ])

  useEffect(() => {
    warmTrendingCache(apiBase).catch(() => {})
  }, [apiBase])

  useEffect(() => {
    if (activeView === 'agents') {
      setDidVisitAgents(true)
    }
  }, [activeView])

  return (
    <section className="workspace-panel">
      <div className="workspace-sprite-track" ref={workspaceSpriteTrackRef} aria-hidden="true">
        <div className="sprite-shell facing-left" ref={workspaceSpriteShellRef}>
          <div className={`sprite-avatar ${spriteMode}`} />
        </div>
      </div>
      {activeView === 'markets' ? <MarketsView apiBase={apiBase} marketRows={marketRows} briefs={briefs} language={language} /> : null}
      {didVisitAgents ? (
        <div style={{ display: activeView === 'agents' ? 'flex' : 'none', flexDirection: 'column', flex: 1, minHeight: 0 }}>
          <AgentsView apiBase={apiBase} language={language} />
        </div>
      ) : null}
      {activeView === 'research' ? <SettingsView language={language} setLanguage={setLanguage} /> : null}
      {activeView === 'wallet' ? <WalletView apiBase={apiBase} language={language} /> : null}
      {!['markets', 'agents', 'research', 'wallet'].includes(activeView) ? <EmptyView /> : null}
    </section>
  )
}
