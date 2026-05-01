import { useEffect, useMemo, useState } from 'react'
import MarketBoard from './MarketBoard'

const DETAIL_INTERVALS = ['1m', '5m', '15m', '1h', '4h', '1d']
const MEME_BANNER_CACHE_KEY = 'meme-banner-cache:v1'
const MEME_BANNER_CACHE_TTL_MS = 10 * 60 * 1000

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
    volBase: '24H Volume',
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
    sessionOpen: '24H Open',
    bestBid: 'Best Bid',
    bestAsk: 'Best Ask',
    spread: 'Spread',
    mid: 'Mid Price',
    rangePct: '24H Range %',
    snapshot: 'Market Snapshot',
    depth: 'Depth Snapshot',
    imbalance: 'Depth Imbalance',
    bidDepth: 'Top 5 Bid Depth',
    askDepth: 'Top 5 Ask Depth',
    candleOpen: 'Open',
    candleClose: 'Close',
    candleHigh: 'High',
    candleLow: 'Low',
    candleVol: 'Volume',
    candleTurnover: 'Turnover',
    candleRange: 'Range %',
    candleChange: 'Change %',
    intervalData: 'Interval Data',
    hoverHint: 'Hover candles to inspect interval stats.',
    live: 'Live',
    of: 'of',
    lastUpdate: 'Last update',
    memeBanner: 'Meme Radar',
    memeBannerCopy: 'SOL and BNB names running hottest over the last 6 hours.',
    hotWindow: '6H Heat',
    hotVolume: '6H Vol',
    hotTxns: '6H Txns',
    hotCap: 'Mkt Cap',
  },
  zh: {
    back: '返回市场',
    timeline: '市场动态',
    timelineCopy: '这条新闻轨道会跟着首页主币种跑，用更像时间线的方式显示新闻。',
    source: '来源',
    loading: '正在加载相关新闻...',
    empty: '这个币暂时还没有抓到新的相关新闻。',
    today: '今天',
    last: '最新价',
    change: '24小时',
    high: '24H最高',
    low: '24H最低',
    volBase: '24H成交量',
    volQuote: '24H成交额',
    chart: '价格图表',
    book: '订单簿',
    open: '打开 OKX',
    bids: '买盘',
    asks: '卖盘',
    price: '价格',
    amount: '数量',
    total: '累计',
    loadingMarket: '正在加载交易终端...',
    sessionOpen: '24H开盘',
    bestBid: '最佳买价',
    bestAsk: '最佳卖价',
    spread: '买卖价差',
    mid: '中间价',
    rangePct: '24H振幅',
    snapshot: '市场快照',
    depth: '深度快照',
    imbalance: '深度失衡',
    bidDepth: '前五档买量',
    askDepth: '前五档卖量',
    candleOpen: '开',
    candleClose: '收',
    candleHigh: '高',
    candleLow: '低',
    candleVol: '成交量',
    candleTurnover: '成交额',
    candleRange: '区间振幅',
    candleChange: '区间涨跌',
    intervalData: '区间数据',
    hoverHint: '鼠标悬停 K 线可查看该周期明细。',
    live: '实时',
    of: '/',
    lastUpdate: '更新时间',
    memeBanner: 'Meme 热榜',
    memeBannerCopy: '最近 6 小时 Solana 和 BNB Chain 最热的 meme。',
    hotWindow: '6H 热度',
    hotVolume: '6H 量',
    hotTxns: '6H 交易',
    hotCap: '市值',
  },
}

function buildMarketUrl(symbol) {
  return `https://www.okx.com/trade-spot/${String(symbol || '').toLowerCase()}-usdt`
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
  return Number(value).toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
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

function formatSignedPercent(value, decimals = 2) {
  const num = Number(value)
  if (!Number.isFinite(num)) return '--'
  return `${num >= 0 ? '+' : ''}${num.toFixed(decimals)}%`
}

function formatTimestamp(ts, language) {
  const value = Number(ts)
  if (!Number.isFinite(value) || value <= 0) return '--'
  const date = new Date(value)
  const locale = language === 'zh' ? 'zh-CN' : 'en-US'
  return date.toLocaleString(locale, {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function calcRangePercent(low, high) {
  const lowNum = Number(low)
  const highNum = Number(high)
  if (!Number.isFinite(lowNum) || !Number.isFinite(highNum) || lowNum <= 0 || highNum <= lowNum) return 0
  return ((highNum - lowNum) / lowNum) * 100
}

function sumDepth(rows, count = 5) {
  return (rows || []).slice(0, count).reduce((sum, row) => sum + Number(row?.size || 0), 0)
}

function depthImbalance(bidDepth, askDepth) {
  const total = Number(bidDepth) + Number(askDepth)
  if (!Number.isFinite(total) || total <= 0) return 0
  return ((Number(bidDepth) - Number(askDepth)) / total) * 100
}

function readMemeBannerCache() {
  if (typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(MEME_BANNER_CACHE_KEY)
    if (!raw) return []
    const payload = JSON.parse(raw)
    const timestamp = Number(payload?.timestamp || 0)
    const items = Array.isArray(payload?.items) ? payload.items : []
    if (!timestamp || !items.length) return []
    if ((Date.now() - timestamp) > MEME_BANNER_CACHE_TTL_MS) return []
    return items
  } catch {
    return []
  }
}

function writeMemeBannerCache(items) {
  if (typeof window === 'undefined' || !Array.isArray(items) || !items.length) return
  try {
    window.localStorage.setItem(
      MEME_BANNER_CACHE_KEY,
      JSON.stringify({ timestamp: Date.now(), items }),
    )
  } catch {
    // ignore cache write failures
  }
}

function buildStatRows(items) {
  return items.map((item) => (
    <div className="market-terminal-stat-item" key={item.label}>
      <span>{item.label}</span>
      <strong className={item.tone || ''}>{item.value}</strong>
    </div>
  ))
}

function KlineChart({ candles, activeIndex, onActiveIndexChange }) {
  const width = 920
  const height = 470
  const priceAreaHeight = 324
  const volumeAreaHeight = 82
  const chartTop = 18
  const chartLeft = 14
  const chartRightPad = 72
  const volumeTop = priceAreaHeight + 34
  const innerWidth = width - chartLeft - chartRightPad
  const step = innerWidth / Math.max(1, candles.length)
  const candleWidth = Math.max(3.5, step * 0.52)
  const highs = candles.map((item) => item.high)
  const lows = candles.map((item) => item.low)
  const vols = candles.map((item) => item.vol)
  const maxHigh = Math.max(...highs)
  const minLow = Math.min(...lows)
  const maxVol = Math.max(...vols, 1)
  const range = Math.max(maxHigh - minLow, 1)
  const selectedIndex = Number.isInteger(activeIndex) ? activeIndex : candles.length - 1
  const activeCandle = candles[selectedIndex] || candles[candles.length - 1]

  const yForPrice = (value) => chartTop + ((maxHigh - value) / range) * (priceAreaHeight - 18)
  const volumeHeight = (value) => (value / maxVol) * volumeAreaHeight

  const handlePointerMove = (event) => {
    const bounds = event.currentTarget.getBoundingClientRect()
    if (!bounds.width || !candles.length) return
    const svgX = ((event.clientX - bounds.left) / bounds.width) * width
    const nextIndex = Math.max(0, Math.min(candles.length - 1, Math.floor((svgX - chartLeft) / step)))
    onActiveIndexChange(nextIndex)
  }

  const activeX = chartLeft + (selectedIndex + 0.5) * step
  const activeY = activeCandle ? yForPrice(activeCandle.close) : chartTop
  const gridLevels = Array.from({ length: 5 }, (_, index) => {
    const ratio = index / 4
    const value = maxHigh - range * ratio
    return { value, y: yForPrice(value) }
  })

  return (
    <svg
      className="market-kline-chart"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      aria-hidden="true"
      onPointerMove={handlePointerMove}
      onPointerLeave={() => onActiveIndexChange(null)}
    >
      {gridLevels.map((level) => (
        <g key={level.y}>
          <line className="market-kline-grid" x1={chartLeft} y1={level.y} x2={width - chartRightPad + 8} y2={level.y} />
          <text className="market-kline-axis-label" x={width - chartRightPad + 14} y={level.y + 4}>
            {formatPrice(level.value)}
          </text>
        </g>
      ))}

      <line className="market-kline-grid volume-divider" x1={chartLeft} y1={volumeTop - 12} x2={width - chartRightPad + 8} y2={volumeTop - 12} />

      {candles.map((candle, index) => {
        const x = chartLeft + (index + 0.5) * step
        const openY = yForPrice(candle.open)
        const closeY = yForPrice(candle.close)
        const highY = yForPrice(candle.high)
        const lowY = yForPrice(candle.low)
        const bodyTop = Math.min(openY, closeY)
        const bodyHeight = Math.max(Math.abs(closeY - openY), 2)
        const up = candle.close >= candle.open
        const color = up ? '#1d8f54' : '#bf3f37'
        const barHeight = volumeHeight(candle.vol)
        return (
          <g key={candle.ts} className={index === selectedIndex ? 'market-kline-candle active' : 'market-kline-candle'}>
            <line className="market-kline-wick" x1={x} y1={highY} x2={x} y2={lowY} stroke={color} />
            <rect className="market-kline-body" x={x - candleWidth / 2} y={bodyTop} width={candleWidth} height={bodyHeight} fill={color} rx="1.4" />
            <rect
              className="market-kline-volume"
              x={x - candleWidth / 2}
              y={volumeTop + volumeAreaHeight - barHeight}
              width={candleWidth}
              height={barHeight}
              fill={color}
              opacity={index === selectedIndex ? '0.6' : '0.34'}
              rx="1.2"
            />
          </g>
        )
      })}

      {activeCandle ? (
        <g className="market-kline-crosshair">
          <line x1={activeX} y1={chartTop} x2={activeX} y2={height - 20} />
          <line x1={chartLeft} y1={activeY} x2={width - chartRightPad + 8} y2={activeY} />
          <circle cx={activeX} cy={activeY} r="4.2" />
        </g>
      ) : null}
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

function MemeBannerPanel({ apiBase, copy }) {
  const [items, setItems] = useState(() => readMemeBannerCache())
  const [loading, setLoading] = useState(() => !readMemeBannerCache().length)
  const marqueeBaseItems = items.length
    ? Array.from({ length: Math.max(2, Math.ceil(14 / items.length)) }, () => items).flat()
    : []
  const marqueeItems = marqueeBaseItems.length ? [...marqueeBaseItems, ...marqueeBaseItems] : []

  useEffect(() => {
    let ignore = false
    const cached = readMemeBannerCache()
    if (cached.length) {
      setItems(cached)
      setLoading(false)
    }

    const load = async () => {
      try {
        const response = await fetch(`${apiBase}/meme/banner?chains=solana,bsc&limit=7`)
        if (!response.ok) throw new Error(`meme banner failed (${response.status})`)
        const payload = await response.json()
        const nextItems = Array.isArray(payload.items) ? payload.items : []
        if (!ignore && nextItems.length) {
          setItems(nextItems)
          writeMemeBannerCache(nextItems)
        }
      } catch (error) {
        console.error('Meme banner fallback', error)
      } finally {
        if (!ignore) setLoading(false)
      }
    }

    load()
    return () => {
      ignore = true
    }
  }, [apiBase])

  return (
    <aside className="market-meme-banner">
      <div className="market-meme-list">
        {loading ? <div className="market-meme-empty">Loading banner...</div> : null}
        {!loading && !items.length ? <div className="market-meme-empty">No meme data.</div> : null}
        {!!items.length ? (
          <div className="market-meme-marquee">
            <div className="market-meme-track">
              {marqueeItems.map((item, index) => {
                const up = Number(item.change6h) >= 0
                return (
                  <a className="market-meme-card" href={item.url} target="_blank" rel="noreferrer" key={`${item.chain}-${item.symbol}-${index}`}>
                    <div className="market-meme-card-top">
                      <span className="market-meme-icon">
                        {item.icon ? <img src={item.icon} alt={item.symbol} /> : <span>{item.symbol?.slice(0, 2)}</span>}
                      </span>
                      <div className="market-meme-main">
                        <div className="market-meme-symbol-row">
                          <strong>{item.symbol}</strong>
                          <span className={`market-meme-change ${up ? 'up' : 'down'}`}>
                            {up ? '+' : ''}{Number(item.change6h || 0).toFixed(2)}%
                          </span>
                        </div>
                        <div className="market-meme-name-row">
                          <span>{item.name}</span>
                          <span className="market-meme-chain">{item.chainLabel}</span>
                        </div>
                      </div>
                    </div>

                    <div className="market-meme-stats">
                      <div className="market-meme-stat">
                        <span>{copy.price}</span>
                        <strong>{item.price}</strong>
                      </div>
                      <div className="market-meme-stat">
                        <span>{copy.hotVolume}</span>
                        <strong>{item.volume6h}</strong>
                      </div>
                      <div className="market-meme-stat">
                        <span>{copy.hotTxns}</span>
                        <strong>{item.txns6h}</strong>
                      </div>
                      <div className="market-meme-stat">
                        <span>{copy.hotCap}</span>
                        <strong>{item.marketCap}</strong>
                      </div>
                    </div>
                  </a>
                )
              })}
            </div>
          </div>
        ) : null}
      </div>
    </aside>
  )
}

function TradingTerminal({ apiBase, coin, interval, onIntervalChange, onBack, copy, language }) {
  const [payload, setPayload] = useState(null)
  const [loading, setLoading] = useState(true)
  const [activeCandleIndex, setActiveCandleIndex] = useState(null)

  useEffect(() => {
    if (!coin) return
    let ignore = false

    const load = async () => {
      try {
        const params = new URLSearchParams({
          symbol: coin.symbol,
          interval,
          candles: '120',
          depth: '18',
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
    setActiveCandleIndex(null)
    load()
    const timer = window.setInterval(load, 5000)
    return () => {
      ignore = true
      window.clearInterval(timer)
    }
  }, [apiBase, coin?.symbol, interval])

  const ticker = payload?.ticker
  const candles = payload?.candles || []
  const asks = (payload?.orderbook?.asks || []).slice(0, 12).reverse()
  const bids = (payload?.orderbook?.bids || []).slice(0, 12)
  const last = Number(ticker?.last || 0)
  const change = formatPercent(ticker?.last, ticker?.open24h)
  const up = change >= 0
  const bestBid = Number(ticker?.bidPx || bids[0]?.price || 0)
  const bestAsk = Number(ticker?.askPx || asks[asks.length - 1]?.price || 0)
  const midPrice = bestBid && bestAsk ? (bestBid + bestAsk) / 2 : 0
  const spreadAbs = bestBid && bestAsk ? Math.max(bestAsk - bestBid, 0) : 0
  const spreadPct = midPrice ? (spreadAbs / midPrice) * 100 : 0
  const rangePct = calcRangePercent(ticker?.low24h, ticker?.high24h)
  const bidDepth = sumDepth(bids, 5)
  const askDepth = sumDepth(asks.slice().reverse(), 5)
  const imbalance = depthImbalance(bidDepth, askDepth)
  const activeCandle = candles[Number.isInteger(activeCandleIndex) ? activeCandleIndex : candles.length - 1] || null
  const candleChange = activeCandle ? formatPercent(activeCandle.close, activeCandle.open) : 0
  const candleRange = activeCandle ? calcRangePercent(activeCandle.low, activeCandle.high) : 0

  const topStats = [
    { label: copy.sessionOpen, value: formatPrice(ticker?.open24h) },
    { label: copy.high, value: formatPrice(ticker?.high24h) },
    { label: copy.low, value: formatPrice(ticker?.low24h) },
    { label: copy.volBase, value: formatCompact(ticker?.vol24h, 2) },
    { label: copy.volQuote, value: formatCompact(ticker?.volCcy24h, 2) },
    { label: copy.bestBid, value: formatPrice(bestBid) },
    { label: copy.bestAsk, value: formatPrice(bestAsk) },
    { label: copy.spread, value: `${formatPrice(spreadAbs)} / ${spreadPct.toFixed(3)}%` },
  ]

  const selectedStats = activeCandle ? [
    { label: copy.candleOpen, value: formatPrice(activeCandle.open) },
    { label: copy.candleHigh, value: formatPrice(activeCandle.high) },
    { label: copy.candleLow, value: formatPrice(activeCandle.low) },
    { label: copy.candleClose, value: formatPrice(activeCandle.close) },
    { label: copy.candleChange, value: formatSignedPercent(candleChange), tone: candleChange >= 0 ? 'up' : 'down' },
    { label: copy.candleRange, value: `${candleRange.toFixed(2)}%` },
    { label: copy.candleVol, value: formatCompact(activeCandle.vol, 2) },
    { label: copy.candleTurnover, value: formatCompact(activeCandle.volCcyQuote, 2) },
  ] : []

  const snapshotStats = [
    { label: copy.last, value: formatPrice(last), tone: up ? 'up' : 'down' },
    { label: copy.change, value: formatSignedPercent(change), tone: up ? 'up' : 'down' },
    { label: copy.mid, value: formatPrice(midPrice) },
    { label: copy.rangePct, value: `${rangePct.toFixed(2)}%` },
  ]

  const depthStats = [
    { label: copy.bidDepth, value: formatCompact(bidDepth, 4) },
    { label: copy.askDepth, value: formatCompact(askDepth, 4) },
    { label: copy.imbalance, value: formatSignedPercent(imbalance, 2), tone: imbalance >= 0 ? 'up' : 'down' },
    { label: copy.lastUpdate, value: formatTimestamp(ticker?.ts, language) },
  ]

  return (
    <div className="workspace-view active market-detail-view">
      <section className="market-terminal-shell">
        <div className="market-terminal-topbar">
          <button className="market-detail-back" type="button" onClick={onBack}>{copy.back}</button>
          <a className="market-focus-link" href={buildMarketUrl(coin.symbol)} target="_blank" rel="noreferrer">{copy.open}</a>
        </div>

        <div className="market-terminal-summary market-terminal-summary-pro">
          <div className="market-terminal-pair">
            <div className="market-terminal-badge">{coin.symbol}</div>
            <div className="market-terminal-pair-copy">
              <div className="market-terminal-symbol">{coin.symbol}/USDT</div>
              <div className="market-terminal-name">{coin.name}</div>
            </div>
          </div>

          <div className="market-terminal-lastblock">
            <div className="market-terminal-live-row">
              <span className="market-live-dot" aria-hidden="true" />
              <span>{copy.live}</span>
            </div>
            <div className={`market-terminal-last ${up ? 'up' : 'down'}`}>{formatPrice(last)}</div>
            <div className={`market-terminal-change ${up ? 'up' : 'down'}`}>{formatSignedPercent(change)}</div>
          </div>

          <div className="market-terminal-stats market-terminal-topstats">
            {buildStatRows(topStats)}
          </div>
        </div>

        <div className="market-terminal-toolbar">
          <div className="market-terminal-intervals">
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
          <div className="market-terminal-toolbar-note">{copy.hoverHint}</div>
        </div>

        {loading ? <div className="market-terminal-loading">{copy.loadingMarket}</div> : null}

        {!loading ? (
          <div className="market-terminal-grid market-terminal-grid-pro">
            <div className="market-terminal-left-stack">
              <section className="market-terminal-panel market-terminal-chart-panel">
                <div className="market-terminal-panel-head market-terminal-panel-head-stack">
                  <div>
                    <div className="market-news-kicker">{copy.chart}</div>
                    <div className="market-terminal-panel-meta">{coin.symbol}/USDT · OKX · {interval}</div>
                  </div>
                  <div className="market-terminal-mini-stats">
                    {buildStatRows(snapshotStats)}
                  </div>
                </div>

                <div className="market-terminal-ohlc-strip">
                  <div className="market-terminal-strip-label">{copy.intervalData}</div>
                  <div className="market-terminal-ohlc-grid">
                    {buildStatRows(selectedStats)}
                  </div>
                </div>

                <div className="market-terminal-chart-wrap">
                  {candles.length ? (
                    <KlineChart
                      candles={candles}
                      activeIndex={activeCandleIndex}
                      onActiveIndexChange={setActiveCandleIndex}
                    />
                  ) : (
                    <div className="market-terminal-empty">No chart data.</div>
                  )}
                </div>
              </section>

              <div className="market-terminal-subgrid">
                <section className="market-terminal-panel market-terminal-subpanel">
                  <div className="market-terminal-panel-head">
                    <div className="market-news-kicker">{copy.snapshot}</div>
                    <div className="market-terminal-panel-meta">{copy.lastUpdate}: {formatTimestamp(ticker?.ts, language)}</div>
                  </div>
                  <div className="market-terminal-stat-grid">
                    {buildStatRows([
                      { label: copy.sessionOpen, value: formatPrice(ticker?.open24h) },
                      { label: copy.mid, value: formatPrice(midPrice) },
                      { label: copy.rangePct, value: `${rangePct.toFixed(2)}%` },
                      { label: copy.volQuote, value: formatCompact(ticker?.volCcy24h, 2) },
                    ])}
                  </div>
                </section>

                <section className="market-terminal-panel market-terminal-subpanel">
                  <div className="market-terminal-panel-head">
                    <div className="market-news-kicker">{copy.depth}</div>
                    <div className="market-terminal-panel-meta">{copy.of} 5 levels</div>
                  </div>
                  <div className="market-terminal-stat-grid">
                    {buildStatRows(depthStats)}
                  </div>
                </section>
              </div>
            </div>

            <section className="market-terminal-panel market-book-panel market-book-panel-pro">
              <div className="market-terminal-panel-head">
                <div className="market-news-kicker">{copy.book}</div>
                <div className={`market-terminal-book-last ${up ? 'up' : 'down'}`}>{formatPrice(last)}</div>
              </div>

              <div className="market-book-summary">
                <div className="market-book-summary-item">
                  <span>{copy.bestBid}</span>
                  <strong className="up">{formatPrice(bestBid)}</strong>
                </div>
                <div className="market-book-summary-item">
                  <span>{copy.bestAsk}</span>
                  <strong className="down">{formatPrice(bestAsk)}</strong>
                </div>
                <div className="market-book-summary-item">
                  <span>{copy.spread}</span>
                  <strong>{formatPrice(spreadAbs)}</strong>
                </div>
              </div>

              <div className="market-book-head">
                <span>{copy.price}</span>
                <span>{copy.amount}</span>
                <span>{copy.total}</span>
              </div>

              <div className="market-book-section asks">
                <div className="market-book-side">{copy.asks}</div>
                <div className="market-book-stack">
                  <OrderRows rows={asks} tone="asks" />
                </div>
              </div>

              <div className={`market-book-mid ${up ? 'up' : 'down'}`}>
                <strong>{formatPrice(last)}</strong>
                <span>{formatPrice(bestBid)} / {formatPrice(bestAsk)}</span>
              </div>

              <div className="market-book-section bids">
                <div className="market-book-side">{copy.bids}</div>
                <div className="market-book-stack">
                  <OrderRows rows={bids} tone="bids" />
                </div>
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
        language={language}
      />
    )
  }

  return (
    <div className="workspace-view active market-home-view">
      <div className="market-home-layout">
        <div className="market-shell">
          <div className="market-home-hero">
            <div className="market-home-main">
              <MarketBoard rows={marketRows} language={language} onSelectCoin={(coin) => setSelectedCoin(coin)} />
            </div>
            <MemeBannerPanel apiBase={apiBase} copy={copy} />
          </div>
        </div>
      </div>
    </div>
  )
}
