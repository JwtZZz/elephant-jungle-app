import { useEffect, useRef, useState } from 'react'
import MarketsView from './MarketsView'
import AgentsView, { warmTrendingCache } from './AgentsView'
import WalletView from './WalletView'
import SettingsView from './SettingsView'
import WorkView from './WorkView'
import { useSpriteOrbit } from '../hooks/useSpriteOrbit'
import { useSpriteHoverNews } from '../hooks/useSpriteHoverNews'
import { useAutoCycleBubble } from '../hooks/useAutoCycleBubble'

function EmptyView() {
  return <div className="workspace-empty" aria-hidden="true" />
}

export default function WorkspacePanel({ activeView, apiBase, marketRows, briefs, language, setLanguage }) {
  const workspaceSpriteTrackRef = useRef(null)
  const workspaceSpriteShellRef = useRef(null)
  const [didVisitAgents, setDidVisitAgents] = useState(activeView === 'agents')
  const { spriteMode, pauseSprite, resumeSprite } = useSpriteOrbit([
    { trackRef: workspaceSpriteTrackRef, shellRef: workspaceSpriteShellRef, direction: -1 },
  ])

  const hoverNews = useSpriteHoverNews(apiBase, 1)
  const workspaceBubble = useAutoCycleBubble(language)
  const bubbleText = hoverNews.isHovered ? hoverNews.bubbleText : workspaceBubble

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
        <div className="sprite-shell facing-left" ref={workspaceSpriteShellRef}
          onMouseEnter={(e) => { hoverNews.handleMouseEnter(e); pauseSprite(0) }}
          onMouseLeave={(e) => { hoverNews.handleMouseLeave(e); resumeSprite(0) }}
        >
          {bubbleText ? <div className="sprite-bubble">{bubbleText}</div> : null}
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
      {activeView === 'work' ? <WorkView apiBase={apiBase} language={language} /> : null}
      {activeView === 'wallet' ? <WalletView apiBase={apiBase} language={language} /> : null}
      {!['markets', 'agents', 'research', 'work', 'wallet'].includes(activeView) ? <EmptyView /> : null}
    </section>
  )
}
