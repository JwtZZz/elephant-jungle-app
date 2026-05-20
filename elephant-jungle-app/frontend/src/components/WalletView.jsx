import { useEffect, useRef, useState } from 'react'

/* ── Mock data ────────────────────────────────────────────────────────────── */

const MOCK_ASSETS = [
  { symbol: 'SOL',    name: 'Solana',    balance: 8.42,    value: 1364.04,  change: 3.2,  color: '#00d18c' },
  { symbol: 'BONK',   name: 'Bonk',      balance: 1250000, value: 312.50,   change: -5.1, color: '#f7931a' },
  { symbol: 'TEST',   name: 'TestCoin',  balance: 5000000, value: 75.00,    change: 0,    color: '#8b5cf6' },
  { symbol: 'PEPE',   name: 'Pepe',      balance: 50000,   value: 12.30,    change: 12.8, color: '#22c55e' },
]

const MOCK_CANDLES = Array.from({ length: 80 }, (_, i) => {
  const base = 155 + Math.sin(i / 12) * 18 + Math.sin(i / 5) * 4 + (i / 80) * 10
  const open = base + (Math.random() - 0.5) * 6
  const close = open + (Math.random() - 0.48) * 10
  const high = Math.max(open, close) + Math.random() * 4
  const low = Math.min(open, close) - Math.random() * 4
  return { ts: Date.now() - (80 - i) * 300000, open, high, low, close, vol: Math.random() * 5000 + 500 }
})

const MOCK_SIGNALS = [
  { time: '09:32', type: 'buy',  price: 157.20, reason: 'Oversold RSI',     status: 'filled' },
  { time: '10:15', type: 'sell', price: 162.80, reason: 'Resistance hit',   status: 'filled' },
  { time: '11:00', type: 'buy',  price: 160.40, reason: 'MA crossover',     status: 'filled' },
  { time: '13:20', type: 'sell', price: 168.10, reason: 'Target reached',   status: 'pending' },
  { time: '14:05', type: 'buy',  price: 165.30, reason: 'Dip buy signal',   status: 'pending' },
]

const MOCK_CHAT = [
  { role: 'assistant', text: 'I can help you analyze the market and execute strategies in real time. Try asking me about price action, trend analysis, or set up automated trading rules.' },
]

const COPY = {
  en: {
    totalValue: 'Total Value',
    assets: 'Assets',
    price: 'Price',
    holdings: 'Holdings',
    value: 'Value',
    change: '24h',
    pnl: 'P&L',
    tradeSignals: 'Strategy Signals',
    time: 'Time',
    type: 'Type',
    reason: 'Reason',
    status: 'Status',
    buy: 'Buy',
    sell: 'Sell',
    filled: 'Filled',
    pending: 'Pending',
    recentTrades: 'Recent Trades',
    chatPlaceholder: 'Ask about strategy, analysis...',
    send: 'Send',
    thinking: 'Thinking...',
    reconnect: 'Reconnect',
  },
  zh: {
    totalValue: '总资产',
    assets: '资产',
    price: '价格',
    holdings: '持仓',
    value: '市值',
    change: '24h',
    pnl: '盈亏',
    tradeSignals: '策略信号',
    time: '时间',
    type: '方向',
    reason: '原因',
    status: '状态',
    buy: '买入',
    sell: '卖出',
    filled: '已成交',
    pending: '待执行',
    recentTrades: '最近成交',
    chatPlaceholder: '咨询策略、行情分析...',
    send: '发送',
    thinking: '思考中...',
    reconnect: '重连',
  },
}

/* ── Mini Sparkline ───────────────────────────────────────────────────────── */

function MiniChart({ data, color = 'var(--accent)' }) {
  if (!data.length) return null
  const w = 80, h = 32, min = Math.min(...data), max = Math.max(...data)
  const rng = Math.max(max - min, 0.001)
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w
    const y = h - ((v - min) / rng) * (h - 4) - 2
    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`
  }).join(' ')
  return (
    <svg className="wallet-mini-chart" width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      <path d={pts} fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

/* ── K-line Chart ─────────────────────────────────────────────────────────── */

function KlineChart({ candles, signals }) {
  const w = 600, h = 260, padL = 8, padR = 28, padT = 12
  const iw = w - padL - padR
  const minP = Math.min(...candles.map(c => c.low)) * 0.998
  const maxP = Math.max(...candles.map(c => c.high)) * 1.002
  const rng = Math.max(maxP - minP, 0.001)
  const step = iw / Math.max(candles.length, 1)
  const cw = Math.max(3, step * 0.55)
  const gridY = [padT, padT + (h - padT) * 0.25, padT + (h - padT) * 0.5, padT + (h - padT) * 0.75, h]
  const gridLabels = [maxP, maxP - rng * 0.25, maxP - rng * 0.5, maxP - rng * 0.75, minP]

  return (
    <svg className="wallet-kline" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      {gridY.map((y, i) => (
        <g key={i}>
          <line x1={padL} y1={y} x2={w - padR} y2={y} stroke="var(--border-soft)" strokeWidth="0.6" />
          <text x={w - padR + 6} y={y + 3} fill="var(--text-tertiary)" fontSize="9">{gridLabels[i].toFixed(1)}</text>
        </g>
      ))}
      {candles.map((c, i) => {
        const x = padL + (i + 0.5) * step
        const up = c.close >= c.open
        const color = up ? '#1d8f54' : '#bf3f37'
        const yT = padT + ((maxP - Math.max(c.open, c.close)) / rng) * (h - padT)
        const hB = Math.max(Math.abs(c.close - c.open) / rng * (h - padT), 1.2)
        const yW = padT + ((maxP - c.high) / rng) * (h - padT)
        const hW = Math.max((c.high - c.low) / rng * (h - padT), 1.2)
        return (
          <g key={i}>
            <line x1={x} y1={yW} x2={x} y2={yW + hW} stroke={color} strokeWidth="0.8" />
            <rect x={x - cw / 2} y={yT} width={cw} height={hB} fill={color} rx="1" />
          </g>
        )
      })}
      {signals.filter(s => s.status === 'filled').map((s, i) => {
        const idx = Math.min(i * 15 + 10, candles.length - 1)
        const c = candles[idx]
        const x = padL + (idx + 0.5) * step
        const y = padT + ((maxP - c.close) / rng) * (h - padT)
        const isBuy = s.type === 'buy'
        return (
          <g key={i}>
            <line x1={x} y1={padT} x2={x} y2={h} stroke={isBuy ? '#1d8f54' : '#bf3f37'} strokeWidth="0.8" strokeDasharray="2,3" opacity="0.5" />
            <circle cx={x} cy={y} r="4" fill={isBuy ? '#1d8f54' : '#bf3f37'} stroke="var(--bg-surface)" strokeWidth="1.5" />
            <text x={x + 6} y={y - 4} fill={isBuy ? '#1d8f54' : '#bf3f37'} fontSize="8" fontWeight="600">{isBuy ? '▲' : '▼'}</text>
          </g>
        )
      })}
    </svg>
  )
}

/* ── Main Component ───────────────────────────────────────────────────────── */

export default function WalletView({ apiBase, language }) {
  const copy = COPY[language] || COPY.en
  const [chats, setChats] = useState(MOCK_CHAT)
  const [input, setInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const chatEndRef = useRef(null)

  /* Auto-scroll chat */
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chats])

  /* Mock wallet info from backend (or defaults) */
  const [walletInfo, setWalletInfo] = useState(null)
  useEffect(() => {
    if (!apiBase) return
    fetch(`${apiBase}/meme/wallet-info`)
      .then(r => r.ok ? r.json() : null)
      .then(d => d?.address ? setWalletInfo(d) : null)
      .catch(() => {})
  }, [apiBase])

  const totalValue = MOCK_ASSETS.reduce((s, a) => s + a.value, 0)

  const formatVal = (n) => {
    if (n >= 1000) return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    if (n >= 1) return `$${n.toFixed(2)}`
    return `$${n.toFixed(4)}`
  }

  const formatCoin = (n) => {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`
    if (n >= 1_000) return `${(n / 1_000).toFixed(2)}K`
    return n.toFixed(n >= 1 ? 2 : 4)
  }

  const handleSend = () => {
    if (!input.trim() || chatLoading) return
    const msg = input.trim()
    setInput('')
    setChats(p => [...p, { role: 'user', text: msg }])
    setChatLoading(true)
    /* Mock AI response */
    setTimeout(() => {
      setChats(p => [...p, { role: 'assistant', text: `Analyzing "${msg}" — I'll monitor the market and alert you when conditions align. Currently SOL is showing bullish momentum on the 1h chart.` }])
      setChatLoading(false)
    }, 1200)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  /* Shorten wallet address */
  const shortAddr = (addr) => addr ? `${addr.slice(0, 6)}...${addr.slice(-4)}` : '--'

  return (
    <div className="workspace-view active wallet-dashboard-view">
      <div className="wallet-dashboard">

        {/* ════════ LEFT: ASSETS ════════ */}
        <div className="wallet-col wallet-col-left">
          <div className="wallet-card-header">
            <h2 className="wallet-card-title">{copy.assets}</h2>
          </div>

          {/* Total balance */}
          <div className="wallet-total-row">
            <span className="wallet-total-label">{copy.totalValue}</span>
            <span className="wallet-total-value">{formatVal(totalValue)}</span>
          </div>

          {/* Wallet address */}
          <div className="wallet-address-row">
            <code className="wallet-address-chip">{walletInfo?.address ? shortAddr(walletInfo.address) : 'Wallet not connected'}</code>
          </div>

          {/* Token list */}
          <div className="wallet-asset-list">
            <div className="wallet-asset-head">
              <span>{copy.holdings}</span>
              <span>{copy.price}</span>
              <span>{copy.value}</span>
            </div>
            {MOCK_ASSETS.map((asset) => (
              <div className="wallet-asset-row" key={asset.symbol}>
                <div className="wallet-asset-info">
                  <span className="wallet-asset-dot" style={{ background: asset.color }} />
                  <div>
                    <div className="wallet-asset-symbol">{asset.symbol}</div>
                    <div className="wallet-asset-name">{asset.name}</div>
                  </div>
                </div>
                <div className="wallet-asset-data">
                  <span className="wallet-asset-balance">{formatCoin(asset.balance)}</span>
                  <span className="wallet-asset-usd">{formatVal(asset.balance * (asset.value / asset.balance))}</span>
                </div>
              </div>
            ))}
          </div>

          {/* Mini chart for each asset */}
          <div className="wallet-spark-section">
            {MOCK_ASSETS.map((asset, i) => (
              <div className="wallet-spark-row" key={asset.symbol}>
                <span className="wallet-spark-label">{asset.symbol}</span>
                <MiniChart
                  data={MOCK_CANDLES.slice(-15).map(c => c.close * (1 + (i - 2) * 0.02))}
                  color={asset.change >= 0 ? '#1d8f54' : '#bf3f37'}
                />
                <span className={`wallet-spark-change ${asset.change >= 0 ? 'up' : 'down'}`}>
                  {asset.change >= 0 ? '+' : ''}{asset.change.toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* ════════ MIDDLE: CHART + SIGNALS ════════ */}
        <div className="wallet-col wallet-col-middle">
          {/* Price header */}
          <div className="wallet-chart-header">
            <div>
              <div className="wallet-chart-pair">SOL/USDT</div>
              <div className="wallet-chart-price">$165.42</div>
              <div className="wallet-chart-change up">+3.21%</div>
            </div>
            <div className="wallet-chart-stats">
              <div><span>24H High</span><strong>$168.80</strong></div>
              <div><span>24H Low</span><strong>$152.10</strong></div>
              <div><span>24H Vol</span><strong>$2.4M</strong></div>
            </div>
          </div>

          {/* K-line chart */}
          <div className="wallet-chart-wrap">
            <KlineChart candles={MOCK_CANDLES} signals={MOCK_SIGNALS} />
          </div>

          {/* Strategy signals */}
          <div className="wallet-panel-section">
            <div className="wallet-panel-section-title">{copy.tradeSignals}</div>
            <div className="wallet-signals-list">
              <div className="wallet-signals-head">
                <span>{copy.time}</span>
                <span>{copy.type}</span>
                <span>{copy.reason}</span>
                <span>{copy.status}</span>
              </div>
              {MOCK_SIGNALS.map((s, i) => (
                <div className={`wallet-signal-row ${s.status}`} key={i}>
                  <span className="wallet-signal-time">{s.time}</span>
                  <span className={`wallet-signal-type ${s.type}`}>{s.type === 'buy' ? copy.buy : copy.sell}</span>
                  <span className="wallet-signal-reason">{s.reason}</span>
                  <span className={`wallet-signal-status ${s.status}`}>{s.status === 'filled' ? copy.filled : copy.pending}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ════════ RIGHT: AI CHAT ════════ */}
        <div className="wallet-col wallet-col-right">
          <div className="wallet-card-header">
            <h2 className="wallet-card-title">AI Strategy</h2>
          </div>

          <div className="wallet-chat-messages">
            {chats.map((msg, i) => (
              <div className={`wallet-chat-msg ${msg.role}`} key={i}>
                {msg.role === 'assistant' ? (
                  <div className="wallet-chat-avatar">AI</div>
                ) : null}
                <div className="wallet-chat-bubble">
                  <p>{msg.text}</p>
                </div>
              </div>
            ))}
            {chatLoading ? (
              <div className="wallet-chat-msg assistant">
                <div className="wallet-chat-avatar">AI</div>
                <div className="wallet-chat-bubble wallet-chat-thinking">{copy.thinking}</div>
              </div>
            ) : null}
            <div ref={chatEndRef} />
          </div>

          <div className="wallet-chat-input-row">
            <input
              className="wallet-chat-input"
              placeholder={copy.chatPlaceholder}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={chatLoading}
            />
            <button
              className="wallet-chat-send"
              type="button"
              onClick={handleSend}
              disabled={chatLoading || !input.trim()}
            >{copy.send}</button>
          </div>
        </div>

      </div>
    </div>
  )
}
