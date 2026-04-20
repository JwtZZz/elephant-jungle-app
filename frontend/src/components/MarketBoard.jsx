function buildSmoothPath(points) {
  if (!points.length) return ''
  if (points.length === 1) return `M${points[0].x.toFixed(2)},${points[0].y.toFixed(2)}`

  let path = `M${points[0].x.toFixed(2)},${points[0].y.toFixed(2)}`
  for (let index = 0; index < points.length - 1; index += 1) {
    const current = points[index]
    const next = points[index + 1]
    const prev = points[index - 1] || current
    const after = points[index + 2] || next
    const cp1x = current.x + (next.x - prev.x) / 6
    const cp1y = current.y + (next.y - prev.y) / 6
    const cp2x = next.x - (after.x - current.x) / 6
    const cp2y = next.y - (after.y - current.y) / 6
    path += ` C${cp1x.toFixed(2)},${cp1y.toFixed(2)} ${cp2x.toFixed(2)},${cp2y.toFixed(2)} ${next.x.toFixed(2)},${next.y.toFixed(2)}`
  }
  return path
}

function Sparkline({ points, trendUp }) {
  const width = 144
  const height = 46
  const min = Math.min(...points)
  const max = Math.max(...points)
  const range = Math.max(1, max - min)
  const coords = points.map((point, index) => ({
    x: (index / Math.max(1, points.length - 1)) * width,
    y: height - (((point - min) / range) * (height - 8) + 4),
  }))
  const stroke = trendUp ? '#1d8f54' : '#b53333'

  return (
    <svg className="market-sparkline" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
      <path d={buildSmoothPath(coords)} fill="none" stroke={stroke} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export default function MarketBoard({ rows }) {
  return (
    <div className="market-board">
      <div className="market-header">
        <div>Asset</div>
        <div>Price</div>
        <div>24h</div>
        <div>Trend</div>
        <div>24h Range</div>
        <div>Market Cap</div>
      </div>
      <div className="market-rows">
        {rows.map((coin) => {
          const trendUp = coin.change >= 0
          const fillWidth = trendUp ? 68 : 44
          return (
            <div className="market-row" key={coin.symbol}>
              <div className="market-asset">
                <div className="market-coin-mark">
                  {coin.image ? <img src={coin.image} alt={coin.symbol} /> : coin.symbol.slice(0, 2)}
                </div>
                <div className="market-asset-text">
                  <div className="market-symbol">{coin.symbol}</div>
                  <div className="market-name">{coin.name}</div>
                </div>
              </div>
              <div className="market-price">{coin.price}</div>
              <div className={`market-change ${trendUp ? 'up' : 'down'}`}>
                {coin.change > 0 ? '+' : ''}
                {Number(coin.change || 0).toFixed(2)}%
              </div>
              <div><Sparkline points={coin.spark?.length ? coin.spark : [1, 1]} trendUp={trendUp} /></div>
              <div className="market-range">
                <div className="market-range-track"><span className="market-range-fill" style={{ width: `${fillWidth}%` }} /></div>
                <div className="market-range-values"><span>{coin.low}</span><span>{coin.high}</span></div>
              </div>
              <div className="market-cap">{coin.cap}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
