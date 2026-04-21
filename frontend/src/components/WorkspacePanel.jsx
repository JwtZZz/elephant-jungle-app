import MarketsView from './MarketsView'
import AgentsView from './AgentsView'

function EmptyView() {
  return <div className="workspace-empty" aria-hidden="true" />
}

export default function WorkspacePanel({ activeView, marketRows, briefs }) {
  return (
    <section className="workspace-panel">
      {activeView === 'markets' ? <MarketsView marketRows={marketRows} briefs={briefs} /> : null}
      {activeView === 'agents' ? <AgentsView /> : null}
      {!['markets', 'agents'].includes(activeView) ? <EmptyView /> : null}
    </section>
  )
}
