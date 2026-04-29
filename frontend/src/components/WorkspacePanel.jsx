import { useRef } from 'react'
import MarketsView from './MarketsView'
import AgentsView from './AgentsView'
import SettingsView from './SettingsView'
import { useSpriteOrbit } from '../hooks/useSpriteOrbit'

function EmptyView() {
  return <div className="workspace-empty" aria-hidden="true" />
}

export default function WorkspacePanel({ activeView, apiBase, marketRows, briefs, language, setLanguage }) {
  const workspaceSpriteTrackRef = useRef(null)
  const workspaceSpriteShellRef = useRef(null)
  const { spriteMode } = useSpriteOrbit([
    { trackRef: workspaceSpriteTrackRef, shellRef: workspaceSpriteShellRef, direction: -1 },
  ])

  return (
    <section className="workspace-panel">
      <div className="workspace-sprite-track" ref={workspaceSpriteTrackRef} aria-hidden="true">
        <div className="sprite-shell facing-left" ref={workspaceSpriteShellRef}>
          <div className={`sprite-avatar ${spriteMode}`} />
        </div>
      </div>
      {activeView === 'markets' ? <MarketsView apiBase={apiBase} marketRows={marketRows} briefs={briefs} language={language} /> : null}
      {activeView === 'agents' ? <AgentsView apiBase={apiBase} language={language} /> : null}
      {activeView === 'research' ? <SettingsView language={language} setLanguage={setLanguage} /> : null}
      {!['markets', 'agents', 'research'].includes(activeView) ? <EmptyView /> : null}
    </section>
  )
}
