import MarketBoard from './MarketBoard'
import NewsPanels from './NewsPanels'

export default function MarketsView({ marketRows, briefs }) {
  return (
    <div className="workspace-view active">
      <div className="market-shell market-shell-atmosphere">
        <div className="market-pixel-haze" aria-hidden="true" />
        <MarketBoard rows={marketRows} />
        <NewsPanels briefs={briefs} />
      </div>
    </div>
  )
}
