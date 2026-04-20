import MarketsView from './MarketsView'

function EmptyView() {
  return <div className="workspace-empty" aria-hidden="true" />
}

export default function WorkspacePanel({ activeView, marketRows, briefs }) {
  return (
    <section className="workspace-panel">
      {activeView === 'markets' ? <MarketsView marketRows={marketRows} briefs={briefs} /> : <EmptyView />}
    </section>
  )
}
