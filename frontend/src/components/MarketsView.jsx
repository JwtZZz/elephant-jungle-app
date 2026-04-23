import { useEffect, useMemo, useState } from 'react'
import MarketBoard from './MarketBoard'
import NewsPanels from './NewsPanels'

const COPY = {
  en: {
    back: 'Markets',
    open: 'Open',
    timeline: 'Market Feed',
    timelineCopy: 'A warm news rail inspired by the CoinGecko feed, tuned to the asset you selected.',
    source: 'source',
    loading: 'Loading market feed...',
    empty: 'No recent feed items were returned for this asset yet.',
    today: 'Today',
    price: 'Price',
    change: '24H',
    range: 'Range',
    cap: 'Mkt Cap',
    low: 'Low',
    high: 'High',
    quote: 'Quote Board',
    trend: 'Trend',
  },
  zh: {
    back: '市场',
    open: '打开',
    timeline: '市场动态',
    timelineCopy: '右侧这条新闻轨道会跟着首页主币种跑，用更像时间线的方式显示新闻。',
    source: '来源',
    loading: '正在加载相关新闻...',
    empty: '这个币暂时还没有抓到新的相关新闻。',
    today: '今天',
    price: '价格',
    change: '24小时',
    range: '区间',
    cap: '市值',
    low: '最低',
    high: '最高',
    quote: '行情板',
    trend: '走势',
  },
}

function buildMarketUrl(coin) {
  const slug = (coin.name || coin.symbol || '').toLowerCase().replace(/[^a-z0-9]+/g, '-')
  return `https://www.coingecko.com/en/coins/${slug}`
}

function formatTimelineTime(value, language) {
  if (!value) return ''
  const normalized = value.replace(' ', 'T') + (value.endsWith('Z') ? '' : 'Z')
  const date = new Date(normalized)
  if (Number.isNaN(date.getTime())) return value
  const diffHours = Math.max(1, Math.round((Date.now() - date.getTime()) / 3600000))
  if (language === 'zh') return `约 ${diffHours} 小时前`
  return `about ${diffHours} hours ago`
}

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

function DetailSparkline({ points, trendUp }) {
  const width = 420
  const height = 124
  const data = points?.length ? points : [1, 1]
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = Math.max(1, max - min)
  const coords = data.map((point, index) => ({
    x: (index / Math.max(1, data.length - 1)) * width,
    y: height - (((point - min) / range) * (height - 20) + 10),
  }))
  const linePath = buildSmoothPath(coords)
  const areaPath = `${linePath} L ${width},${height - 6} L 0,${height - 6} Z`
  const stroke = trendUp ? '#1d8f54' : '#b53333'
  const gradientId = `detail-fill-${trendUp ? 'up' : 'down'}`
  const dotId = `detail-dot-${trendUp ? 'up' : 'down'}`

  return (
    <svg className="market-detail-sparkline" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.22" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path className="market-detail-area" d={areaPath} fill={`url(#${gradientId})`} />
      <path className="market-detail-path-glow" d={linePath} fill="none" stroke={stroke} strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" />
      <path className="market-detail-path" d={linePath} fill="none" stroke={stroke} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" pathLength="100" />
      <circle className="market-detail-dot" id={dotId} r="4.5" fill={stroke}>
        <animateMotion dur="5.6s" repeatCount="indefinite" rotate="auto">
          <mpath href={`#${dotId}-path`} />
        </animateMotion>
      </circle>
      <path id={`${dotId}-path`} d={linePath} fill="none" stroke="transparent" strokeWidth="0" />
    </svg>
  )
}

function TimelinePanel({ apiBase, coin, copy, language }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!coin) return
    let ignore = false
    const loadTimeline = async () => {
      setLoading(true)
      try {
        const params = new URLSearchParams({ symbol: coin.symbol, name: coin.name, language: 'zh' })
        const response = await fetch(`${apiBase}/market/timeline?${params.toString()}`)
        if (!response.ok) throw new Error(`timeline request failed (${response.status})`)
        const payload = await response.json()
        if (!ignore) setItems(Array.isArray(payload.items) ? payload.items : [])
      } catch (error) {
        console.error('Timeline fallback', error)
        if (!ignore) setItems([])
      } finally {
        if (!ignore) setLoading(false)
      }
    }
    loadTimeline()
    return () => {
      ignore = true
    }
  }, [apiBase, coin?.name, coin?.symbol])

  return (
    <aside className="market-timeline-card">
      <div className="market-news-kicker">{copy.timeline}</div>
      <div className="market-timeline-copy">{copy.timelineCopy}</div>
      <div className="market-timeline-day">{copy.today}</div>
      <div className="market-timeline-list">
        {loading ? <div className="market-timeline-empty">{copy.loading}</div> : null}
        {!loading && !items.length ? <div className="market-timeline-empty">{copy.empty}</div> : null}
        {items.map((item, index) => (
          <a className="market-timeline-item" href={item.url} target="_blank" rel="noreferrer" key={`${item.url}-${index}`}>
            <div className="market-timeline-rail" aria-hidden="true"><span className="market-timeline-dot" /></div>
            <div className="market-timeline-body">
              <div className="market-timeline-time">{formatTimelineTime(item.published_at, language)}</div>
              <div className="market-timeline-title">{item.title}</div>
              {item.original_title && item.original_title !== item.title ? (
                <div className="market-timeline-title-en">{item.original_title}</div>
              ) : null}
              <div className="market-timeline-source">
                {item.source_icon ? <img src={item.source_icon} alt={item.source || copy.source} /> : null}
                <span>{item.source || copy.source}</span>
              </div>
            </div>
          </a>
        ))}
      </div>
    </aside>
  )
}

export default function MarketsView({ apiBase, marketRows, briefs, language }) {
  const copy = COPY[language] || COPY.en
  const [selectedSymbol, setSelectedSymbol] = useState(null)
  const homeTimelineCoin = marketRows[0] || null

  const selectedCoin = useMemo(() => marketRows.find((coin) => coin.symbol === selectedSymbol) || null, [marketRows, selectedSymbol])

  if (selectedCoin) {
    const trendUp = Number(selectedCoin.change || 0) >= 0
    return (
      <div className="workspace-view active market-detail-view">
        <section className="market-detail-shell market-detail-shell-single">
          <div className="market-detail-main market-terminal-shell">
            <div className="market-terminal-topbar">
              <button className="market-detail-back" type="button" onClick={() => setSelectedSymbol(null)}>{copy.back}</button>
              <a className="market-focus-link" href={buildMarketUrl(selectedCoin)} target="_blank" rel="noreferrer">{copy.open}</a>
            </div>
            <section className="market-terminal-card">
              <div className="market-terminal-head">
                <div className="market-terminal-ident">
                  <div className="market-terminal-symbol">{selectedCoin.symbol}</div>
                  <div className="market-terminal-name">{selectedCoin.name}</div>
                </div>
                <div className="market-terminal-priceblock">
                  <div className="market-terminal-price">{selectedCoin.price}</div>
                  <div className={`market-terminal-change ${trendUp ? 'up' : 'down'}`}>
                    {Number(selectedCoin.change || 0) > 0 ? '+' : ''}{Number(selectedCoin.change || 0).toFixed(2)}%
                  </div>
                </div>
              </div>
              <div className="market-terminal-grid">
                <div className="market-terminal-panel market-terminal-quote">
                  <div className="market-news-kicker">{copy.quote}</div>
                  <div className="market-terminal-table">
                    <div><span>{copy.price}</span><strong>{selectedCoin.price}</strong></div>
                    <div><span>{copy.change}</span><strong className={trendUp ? 'up' : 'down'}>{Number(selectedCoin.change || 0) > 0 ? '+' : ''}{Number(selectedCoin.change || 0).toFixed(2)}%</strong></div>
                    <div><span>{copy.low}</span><strong>{selectedCoin.low}</strong></div>
                    <div><span>{copy.high}</span><strong>{selectedCoin.high}</strong></div>
                    <div><span>{copy.range}</span><strong>{selectedCoin.low} - {selectedCoin.high}</strong></div>
                    <div><span>{copy.cap}</span><strong>{selectedCoin.cap}</strong></div>
                  </div>
                </div>
                <div className="market-terminal-panel market-terminal-trend">
                  <div className="market-news-kicker">{copy.trend}</div>
                  <DetailSparkline points={selectedCoin.spark} trendUp={trendUp} />
                </div>
              </div>
            </section>
          </div>
        </section>
      </div>
    )
  }

  return (
    <div className="workspace-view active">
      <div className="market-home-layout">
        <div className="market-shell market-shell-atmosphere">
          <div className="market-pixel-haze" aria-hidden="true" />
          <MarketBoard rows={marketRows} language={language} onSelectCoin={(coin) => setSelectedSymbol(coin.symbol)} />
          <NewsPanels briefs={briefs} language={language} />
        </div>
        {homeTimelineCoin ? <TimelinePanel apiBase={apiBase} coin={homeTimelineCoin} copy={copy} language={language} /> : null}
      </div>
    </div>
  )
}
