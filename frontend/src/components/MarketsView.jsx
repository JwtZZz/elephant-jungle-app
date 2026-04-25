import { useEffect, useMemo, useState } from 'react'
import MarketBoard from './MarketBoard'
import NewsPanels from './NewsPanels'

const DETAIL_INTERVALS = ['1m', '5m', '15m', '1h', '4h', '1d']

const COPY = {
  en: {
    back: 'Back',
    timeline: 'Market Feed',
    timelineCopy: 'A warm news rail inspired by the CoinGecko feed, tuned to the asset you selected.',
    source: 'Source',
    loading: 'Loading market feed...',
    empty: 'No recent feed items were returned for this asset yet.',
    today: 'Today',
    last: 'Last',
    change: '24H',
    high: '24H High',
    low: '24H Low',
    volBase: '24H Vol',
    volQuote: '24H Turnover',
    chart: 'Price Chart',
    book: 'Order Book',
    open: 'Open OKX',
    bids: 'Bids',
    asks: 'Asks',
    price: 'Price',
    amount: 'Size',
    total: 'Total',
    loadingMarket: 'Loading market terminal...',
  },
  zh: {
    back: '返回市场',
    timeline: '市场动态',
    timelineCopy: '右侧这条新闻轨道会跟着首页主币种跑，用更像时间线的方式显示新闻。',
    source: '来源',
    loading: '正在加载相关新闻...',
    empty: '这个币暂时还没有抓到新的相关新闻。',
    today: '今天',
    last: '最新价',
    change: '24小时',
    high: '24H最高',
    low: '24H最低',
    volBase: '24H量',
    volQuote: '24H额',
    chart: 'K线',
    book: '盘口',
    open: '打开 OKX',
    bids: '买盘',
    asks: '卖盘',
    price: '价格',
    amount: '数量',
    total: '累计',
    loadingMarket: '正在加载交易终端...',
  },
}

function buildMarketUrl(symbol) {
  return `https://www.okx.com/trade-spot/${symbol.toLowerCase()}-usdt`
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

function formatNumber(value, decimals = 2) {
  if (!Number.isFinite(Number(value))) return '--'
  return Number(value).toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

function formatCompact(value, decimals = 2) {
  const num = Number(value)
  if (!Number.isFinite(num)) return '--'
  if (num >= 1_000_000_000) return `${(num / 1_000_000_000).toFixed(decimals)}B`
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(decimals)}M`
  if (num >= 1_000) return `${(num / 1_000).toFixed(decimals)}K`
  return num.toFixed(decimals)
}

function formatPrice(value) {
  const num = Number(value)
  if (!Number.isFinite(num)) return '--'
  if (num >= 1000) return formatNumber(num, 1)
  if (num >= 1) return formatNumber(num, 4)
  return formatNumber(num, 6)
}

function formatPercent(last, open) {
  const l = Number(last)
  const o = Number(open)
  if (!Number.isFinite(l) || !Number.isFinite(o) || o === 0) return 0
  return ((l - o) / o) * 100
}

function KlineChart({ candles }) {
  const width = 920
  const height = 470
  const priceAreaHeight = 340
  const volumeAreaHeight = 82
  const chartTop = 20
  const chartLeft = 16
  const chartRightPad = 76
  const volumeTop = priceAreaHeight + 28
  const innerWidth = width - chartLeft - chartRightPad
  const candleWidth = Math.max(4, innerWidth / Math.max(1, candles.length) * 0.62)
  const highs = candles.map((item) => item.high)
  const lows = candles.map((item) => item.low)
  const vols = candles.map((item) => item.vol)
  const maxHigh = Math.max(...highs)
  const minLow = Math.min(...lows)
  const maxVol = Math.max(...vols, 1)
  const range = Math.max(maxHigh - minLow, 1)

  const yForPrice = (value) => chartTop + ((maxHigh - value) / range) * (priceAreaHeight - 24)
  const volumeHeight = (value) => (value / maxVol) * volumeAreaHeight
  const gridLevels = Array.from({ length: 5 }, (_, index) => {
    const ratio = index / 4
    const value = maxHigh - range * ratio
    return { value, y: yForPrice(value) }
  })

  return (
    <svg className="market-kline-chart" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
      {gridLevels.map((level) => (
        <g key={level.y}>
          <line className="market-kline-grid" x1={chartLeft} y1={level.y} x2={width - chartRightPad + 8} y2={level.y} />
          <text className="market-kline-axis-label" x={width - chartRightPad + 16} y={level.y + 4}>
            {formatPrice(level.value)}
          </text>
        </g>
      ))}
      <line className="market-kline-grid volume-divider" x1={chartLeft} y1={volumeTop - 12} x2={width - chartRightPad + 8} y2={volumeTop - 12} />
      {candles.map((candle, index) => {
        const x = chartLeft + (index + 0.5) * (innerWidth / candles.length)
        const openY = yForPrice(candle.open)
        const closeY = yForPrice(candle.close)
        const highY = yForPrice(candle.high)
        const lowY = yForPrice(candle.low)
        const bodyTop = Math.min(openY, closeY)
        const bodyHeight = Math.max(Math.abs(closeY - openY), 2)
        const up = candle.close >= candle.open
        const color = up ? '#1d8f54' : '#b53333'
        const barHeight = volumeHeight(candle.vol)
        return (
          <g key={candle.ts}>
            <line className="market-kline-wick" x1={x} y1={highY} x2={x} y2={lowY} stroke={color} />
            <rect className="market-kline-body" x={x - candleWidth / 2} y={bodyTop} width={candleWidth} height={bodyHeight} fill={color} rx="1.6" />
            <rect className="market-kline-volume" x={x - candleWidth / 2} y={volumeTop + volumeAreaHeight - barHeight} width={candleWidth} height={barHeight} fill={color} opacity="0.42" rx="1.2" />
          </g>
        )
      })}
    </svg>
  )
}

function OrderRows({ rows, tone }) {
  let running = 0
  const maxTotal = rows.reduce((sum, row) => sum + Number(row.size || 0), 0) || 1
  return rows.map((row) => {
    running += Number(row.size || 0)
    const width = `${Math.max(8, (running / maxTotal) * 100)}%`
    return (
      <div className={`market-book-row ${tone}`} key={`${tone}-${row.price}-${row.size}`}>
        <span className="market-book-depth" style={{ width }} aria-hidden="true" />
        <span className="market-book-price">{formatPrice(row.price)}</span>
        <span className="market-book-size">{formatCompact(row.size, 4)}</span>
        <span className="market-book-total">{formatCompact(running, 4)}</span>
      </div>
    )
  })
}

function getTimelineCacheKey(symbol, language) {
  return `market-timeline:${String(symbol || '').toUpperCase()}:${language || 'zh'}`
}

function readTimelineCache(symbol, language) {
  if (typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(getTimelineCacheKey(symbol, language))
    if (!raw) return []
    const payload = JSON.parse(raw)
    const timestamp = Number(payload?.timestamp || 0)
    const items = Array.isArray(payload?.items) ? payload.items : []
    if (!timestamp || !items.length) return []
    if ((Date.now() - timestamp) > 15 * 60 * 1000) return []
    return items
  } catch {
    return []
  }
}

function writeTimelineCache(symbol, language, items) {
  if (typeof window === 'undefined' || !Array.isArray(items) || !items.length) return
  try {
    window.localStorage.setItem(
      getTimelineCacheKey(symbol, language),
      JSON.stringify({ timestamp: Date.now(), items }),
    )
  } catch {
    // ignore cache write failures
  }
}

function TimelinePanel({ apiBase, coin, copy, language }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!coin) return
    let ignore = false
    const cachedItems = readTimelineCache(coin.symbol, 'zh')

    if (cachedItems.length) {
      setItems(cachedItems)
      setLoading(false)
    } else {
      setItems([])
      setLoading(true)
    }

    const loadTimeline = async () => {
      try {
        const params = new URLSearchParams({ symbol: coin.symbol, name: coin.name, language: 'zh' })
        const response = await fetch(`${apiBase}/market/timeline?${params.toString()}`)
        if (!response.ok) throw new Error(`timeline request failed (${response.status})`)
        const payload = await response.json()
        const nextItems = Array.isArray(payload.items) ? payload.items : []
        if (!ignore) {
          setItems(nextItems)
          writeTimelineCache(coin.symbol, 'zh', nextItems)
        }
      } catch (error) {
        console.error('Timeline fallback', error)
        if (!ignore && !cachedItems.length) setItems([])
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

function TradingTerminal({ apiBase, coin, interval, onIntervalChange, onBack, copy }) {
  const [payload, setPayload] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!coin) return
    let ignore = false

    const load = async () => {
      try {
        const params = new URLSearchParams({
          symbol: coin.symbol,
          interval,
          candles: '96',
          depth: '12',
        })
        const response = await fetch(`${apiBase}/market/okx-detail?${params.toString()}`)
        if (!response.ok) throw new Error(`okx detail request failed (${response.status})`)
        const nextPayload = await response.json()
        if (!ignore) {
          setPayload(nextPayload)
          setLoading(false)
        }
      } catch (error) {
        console.error('OKX detail fallback', error)
        if (!ignore) setLoading(false)
      }
    }

    setLoading(true)
    load()
    const timer = window.setInterval(load, 5000)
    return () => {
      ignore = true
      window.clearInterval(timer)
    }
  }, [apiBase, coin?.symbol, interval])

  const ticker = payload?.ticker
  const candles = payload?.candles || []
  const asks = (payload?.orderbook?.asks || []).slice().reverse()
  const bids = payload?.orderbook?.bids || []
  const last = Number(ticker?.last || 0)
  const change = formatPercent(ticker?.last, ticker?.open24h)
  const up = change >= 0

  return (
    <div className="workspace-view active market-detail-view">
      <section className="market-terminal-shell">
        <div className="market-terminal-topbar">
          <button className="market-detail-back" type="button" onClick={onBack}>{copy.back}</button>
          <a className="market-focus-link" href={buildMarketUrl(coin.symbol)} target="_blank" rel="noreferrer">{copy.open}</a>
        </div>

        <div className="market-terminal-summary">
          <div className="market-terminal-pair">
            <div className="market-terminal-badge">{coin.symbol}</div>
            <div>
              <div className="market-terminal-symbol">{coin.symbol}/USDT</div>
              <div className="market-terminal-name">{coin.name}</div>
            </div>
          </div>
          <div className="market-terminal-lastblock">
            <div className={`market-terminal-last ${up ? 'up' : 'down'}`}>{formatPrice(last)}</div>
            <div className={`market-terminal-change ${up ? 'up' : 'down'}`}>{up ? '+' : ''}{change.toFixed(2)}%</div>
          </div>
          <div className="market-terminal-stats">
            <div><span>{copy.high}</span><strong>{formatPrice(ticker?.high24h)}</strong></div>
            <div><span>{copy.low}</span><strong>{formatPrice(ticker?.low24h)}</strong></div>
            <div><span>{copy.volBase}</span><strong>{formatCompact(ticker?.vol24h, 2)}</strong></div>
            <div><span>{copy.volQuote}</span><strong>{formatCompact(ticker?.volCcy24h, 2)}</strong></div>
          </div>
        </div>

        <div className="market-terminal-toolbar">
          {DETAIL_INTERVALS.map((item) => (
            <button
              key={item}
              type="button"
              className={`market-interval-pill ${interval === item ? 'active' : ''}`}
              onClick={() => onIntervalChange(item)}
            >
              {item}
            </button>
          ))}
        </div>

        {loading ? <div className="market-terminal-loading">{copy.loadingMarket}</div> : null}

        {!loading ? (
          <div className="market-terminal-grid">
            <section className="market-terminal-panel market-terminal-chart-panel">
              <div className="market-terminal-panel-head">
                <div className="market-news-kicker">{copy.chart}</div>
                <div className="market-terminal-panel-meta">{coin.symbol}/USDT ? OKX ? {interval}</div>
              </div>
              <div className="market-terminal-chart-wrap">
                {candles.length ? <KlineChart candles={candles} /> : <div className="market-terminal-empty">No chart data.</div>}
              </div>
            </section>

            <section className="market-terminal-panel market-terminal-book-panel">
              <div className="market-terminal-panel-head">
                <div className="market-news-kicker">{copy.book}</div>
                <div className={`market-terminal-book-last ${up ? 'up' : 'down'}`}>{formatPrice(last)}</div>
              </div>
              <div className="market-book-head">
                <span>{copy.price}</span>
                <span>{copy.amount}</span>
                <span>{copy.total}</span>
              </div>
              <div className="market-book-section asks">
                <div className="market-book-side">{copy.asks}</div>
                <OrderRows rows={asks} tone="asks" />
              </div>
              <div className={`market-book-mid ${up ? 'up' : 'down'}`}>
                <strong>{formatPrice(last)}</strong>
                <span>{formatPrice(ticker?.bidPx)} / {formatPrice(ticker?.askPx)}</span>
              </div>
              <div className="market-book-section bids">
                <div className="market-book-side">{copy.bids}</div>
                <OrderRows rows={bids} tone="bids" />
              </div>
            </section>
          </div>
        ) : null}
      </section>
    </div>
  )
}

export default function MarketsView({ apiBase, marketRows, briefs, language }) {
  const copy = COPY[language] || COPY.en
  const [selectedCoin, setSelectedCoin] = useState(null)
  const [selectedInterval, setSelectedInterval] = useState('15m')
  const homeTimelineCoin = marketRows[0] || null

  const activeCoin = useMemo(() => {
    if (!selectedCoin) return null
    return marketRows.find((item) => item.symbol === selectedCoin.symbol) || selectedCoin
  }, [marketRows, selectedCoin])

  if (activeCoin) {
    return (
      <TradingTerminal
        apiBase={apiBase}
        coin={activeCoin}
        interval={selectedInterval}
        onIntervalChange={setSelectedInterval}
        onBack={() => setSelectedCoin(null)}
        copy={copy}
      />
    )
  }

  return (
    <div className="workspace-view active">
      <div className="market-home-layout">
        <div className="market-shell market-shell-atmosphere">
          <div className="market-pixel-haze" aria-hidden="true" />
          <MarketBoard rows={marketRows} language={language} onSelectCoin={(coin) => setSelectedCoin(coin)} />
          <NewsPanels briefs={briefs} language={language} />
        </div>
        {homeTimelineCoin ? <TimelinePanel apiBase={apiBase} coin={homeTimelineCoin} copy={copy} language={language} /> : null}
      </div>
    </div>
  )
}
