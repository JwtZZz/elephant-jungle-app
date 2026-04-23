import { useRef } from 'react'

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
  const linePath = buildSmoothPath(coords)
  const stroke = trendUp ? '#1d8f54' : '#b53333'
  const dotId = `market-dot-${trendUp ? 'up' : 'down'}-${Math.round(points[0] || 0)}-${points.length}`

  return (
    <svg className="market-sparkline" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
      <path className="market-sparkline-glow" d={linePath} fill="none" stroke={stroke} strokeWidth="5.6" strokeLinecap="round" strokeLinejoin="round" />
      <path className="market-sparkline-line" d={linePath} fill="none" stroke={stroke} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" pathLength="100" />
      <circle className="market-sparkline-dot" r="2.6" fill={stroke}>
        <animateMotion dur="4.6s" repeatCount="indefinite" rotate="auto">
          <mpath href={`#${dotId}`} />
        </animateMotion>
      </circle>
      <path id={dotId} d={linePath} fill="none" stroke="transparent" strokeWidth="0" />
    </svg>
  )
}

const HEADERS = {
  en: ['Asset', 'Price', '24h', 'Trend', '24h Range', 'Market Cap'],
  zh: ['资产', '价格', '24小时', '趋势', '24小时区间', '市值'],
}

export default function MarketBoard({ rows, language, onSelectCoin }) {
  const boardRef = useRef(null)
  const frameRef = useRef(0)
  const headers = HEADERS[language] || HEADERS.en

  const handleMove = (event) => {
    const board = boardRef.current
    if (!board) return

    const rect = board.getBoundingClientRect()
    const offsetX = event.clientX - rect.left
    const offsetY = event.clientY - rect.top
    const px = offsetX / rect.width - 0.5
    const py = offsetY / rect.height - 0.5
    const rotateY = px * 5.2
    const rotateX = py * -5.2

    if (frameRef.current) cancelAnimationFrame(frameRef.current)
    frameRef.current = requestAnimationFrame(() => {
      board.style.setProperty('--tilt-rotate-x', `${rotateX.toFixed(2)}deg`)
      board.style.setProperty('--tilt-rotate-y', `${rotateY.toFixed(2)}deg`)
      board.style.setProperty('--tilt-glow-x', `${(offsetX / rect.width) * 100}%`)
      board.style.setProperty('--tilt-glow-y', `${(offsetY / rect.height) * 100}%`)
    })
  }

  const handleLeave = () => {
    const board = boardRef.current
    if (!board) return
    if (frameRef.current) cancelAnimationFrame(frameRef.current)

    board.style.setProperty('--tilt-rotate-x', '0deg')
    board.style.setProperty('--tilt-rotate-y', '0deg')
    board.style.setProperty('--tilt-glow-x', '50%')
    board.style.setProperty('--tilt-glow-y', '32%')
  }

  return (
    <div className="market-board" ref={boardRef} onMouseMove={handleMove} onMouseLeave={handleLeave}>
      <div className="market-board-sheen" aria-hidden="true" />
      <div className="market-header">
        {headers.map((header) => (
          <div key={header}>{header}</div>
        ))}
      </div>
      <div className="market-rows">
        {rows.map((coin) => {
          const trendUp = coin.change >= 0
          const fillWidth = trendUp ? 68 : 44
          return (
            <button className="market-row market-row-button" key={coin.symbol} type="button" onClick={() => onSelectCoin?.(coin)}>
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
            </button>
          )
        })}
      </div>
    </div>
  )
}
