import MarketsView from './MarketsView'
import AgentsView from './AgentsView'
import SettingsView from './SettingsView'

function EmptyView() {
  return <div className="workspace-empty" aria-hidden="true" />
}

export default function WorkspacePanel({ activeView, apiBase, marketRows, briefs, language, setLanguage }) {
  return (
    <section className="workspace-panel">
      {activeView === 'markets' ? <MarketsView apiBase={apiBase} marketRows={marketRows} briefs={briefs} language={language} /> : null}
      {activeView === 'agents' ? <AgentsView language={language} /> : null}
      {activeView === 'research' ? <SettingsView language={language} setLanguage={setLanguage} /> : null}
      {!['markets', 'agents', 'research'].includes(activeView) ? <EmptyView /> : null}
    </section>
  )
}
