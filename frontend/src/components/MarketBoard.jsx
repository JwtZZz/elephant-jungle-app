const COPY = {
  en: {
    asset: 'Asset',
    price: 'Price',
    change: '24h',
    trend: 'Trend',
    low: 'Low',
    high: 'High',
    range: 'Range',
    spread: 'Band',
    cap: 'Market Cap',
  },
  zh: {
    asset: '资产',
    price: '价格',
    change: '24小时',
    trend: '趋势',
    low: '低点',
    high: '高点',
    range: '区间',
    spread: '波动',
    cap: '市值',
  },
}

function sparkPath(values) {
  const points = Array.isArray(values) ? values.filter((value) => Number.isFinite(Number(value))).map(Number) : []
  if (!points.length) return ''
  if (points.length === 1) return 'M 0 23 L 100 23'

  const min = Math.min(...points)
  const max = Math.max(...points)
  const range = Math.max(max - min, 1e-9)

  return points
    .map((value, index) => {
      const x = (index / (points.length - 1)) * 100
      const y = 44 - (((value - min) / range) * 34 + 5)
      return `${index === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`
    })
    .join(' ')
}

function parseMoney(value) {
  return Number(String(value).replace(/[$,]/g, ''))
}

function compactMoneyLabel(value) {
  const number = parseMoney(value)
  if (!Number.isFinite(number)) return '--'
  if (number >= 1000000) return `$${(number / 1000000).toFixed(2)}M`
  if (number >= 1000) return `$${(number / 1000).toFixed(number >= 10000 ? 1 : 2)}K`
  if (number >= 1) return `$${number.toFixed(number >= 100 ? 0 : number >= 10 ? 1 : 2)}`
  return `$${number.toFixed(4)}`
}

function rangeDeltaLabel(low, high) {
  const lowNum = parseMoney(low)
  const highNum = Number(String(high).replace(/[$,]/g, ''))
  if (![lowNum, highNum].every(Number.isFinite) || highNum <= lowNum) return '--'
  return compactMoneyLabel(highNum - lowNum)
}

function rangeSpreadLabel(low, high, copy) {
  const lowNum = parseMoney(low)
  const highNum = parseMoney(high)
  if (![lowNum, highNum].every(Number.isFinite) || lowNum <= 0 || highNum <= lowNum) return '--'
  const ratio = ((highNum - lowNum) / lowNum) * 100
  return `${copy.spread} ${ratio.toFixed(ratio >= 10 ? 1 : 2)}%`
}

export default function MarketBoard({ rows, language, onSelectCoin }) {
  const copy = COPY[language] || COPY.en

  const handlePointerMove = (event) => {
    const board = event.currentTarget
    const bounds = board.getBoundingClientRect()
    const x = (event.clientX - bounds.left) / bounds.width
    const y = (event.clientY - bounds.top) / bounds.height
    board.style.setProperty('--tilt-rotate-x', `${((0.5 - y) * 6).toFixed(2)}deg`)
    board.style.setProperty('--tilt-rotate-y', `${((x - 0.5) * 8).toFixed(2)}deg`)
    board.style.setProperty('--tilt-glow-x', `${(x * 100).toFixed(2)}%`)
    board.style.setProperty('--tilt-glow-y', `${(y * 100).toFixed(2)}%`)
  }

  const resetTilt = (event) => {
    const board = event.currentTarget
    board.style.setProperty('--tilt-rotate-x', '0deg')
    board.style.setProperty('--tilt-rotate-y', '0deg')
    board.style.setProperty('--tilt-glow-x', '50%')
    board.style.setProperty('--tilt-glow-y', '32%')
  }

  return (
    <section className="market-board" onPointerMove={handlePointerMove} onPointerLeave={resetTilt}>
      <div className="market-board-sheen" aria-hidden="true" />
      <div className="market-header">
        <div>{copy.asset}</div>
        <div>{copy.price}</div>
        <div>{copy.change}</div>
        <div>{copy.trend}</div>
        <div>{copy.low}</div>
        <div>{copy.high}</div>
        <div>{copy.range}</div>
        <div>{copy.spread}</div>
        <div>{copy.cap}</div>
      </div>

      <div className="market-rows">
        {rows.map((row) => {
          const isUp = Number(row.change) >= 0
          return (
            <button
              key={row.symbol}
              type="button"
              className="market-row market-row-button"
              onClick={() => onSelectCoin(row)}
            >
              <div className="market-asset">
                <span className="market-coin-mark">
                  {row.image ? <img src={row.image} alt={row.symbol} /> : row.symbol?.slice(0, 1)}
                </span>
                <span>
                  <div className="market-symbol">{row.symbol}</div>
                  <div className="market-name">{row.name}</div>
                </span>
              </div>

              <div className="market-price">{row.price}</div>
              <div className={`market-change ${isUp ? 'up' : 'down'}`}>{isUp ? '+' : ''}{Number(row.change).toFixed(2)}%</div>

              <div className="market-trend">
                <svg className="market-sparkline" viewBox="0 0 100 46" preserveAspectRatio="none" aria-hidden="true">
                  <path
                    d={sparkPath(row.spark)}
                    fill="none"
                    stroke={isUp ? '#1d8f54' : '#bf3f37'}
                    strokeWidth="2.3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </div>

              <div className="market-metric market-price-compact">{compactMoneyLabel(row.low)}</div>
              <div className="market-metric market-price-compact">{compactMoneyLabel(row.high)}</div>
              <div className="market-metric">{rangeDeltaLabel(row.low, row.high)}</div>
              <div className="market-metric">{rangeSpreadLabel(row.low, row.high, copy).replace(`${copy.spread} `, '')}</div>
              <div className="market-cap">{row.cap}</div>
            </button>
          )
        })}
      </div>
    </section>
  )
}
