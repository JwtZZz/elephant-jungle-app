import { useCallback, useEffect, useMemo, useState } from 'react'

const COPY = {
  en: {
    title: 'Simulated Trading',
    balance: 'Balance',
    pnl: 'Total P&L',
    positions: 'Positions',
    noPositions: 'No open positions',
    orders: 'Order History',
    noOrders: 'No orders yet',
    asset: 'Asset',
    quantity: 'Qty',
    entryPrice: 'Entry',
    marketValue: 'Market Val',
    side: 'Side',
    price: 'Price',
    total: 'Total',
    time: 'Time',
    buy: 'Buy',
    sell: 'Sell',
    loading: 'Loading...',
    loginRequired: 'Please log in to use simulated trading.',
    error: 'Failed to load data',
    reasoning: 'Note',
    winRate: 'Win Rate',
    totalTrades: 'Trades',
    lastUpdate: 'Last updated',
    retry: 'Retry',
    portfolio: 'Portfolio',
    equityCurve: 'Equity Curve',
    pnlShort: 'P&L',
    usdt: 'USDT',
    openPositions: 'Open Positions',
    recentOrders: 'Recent Orders',
    unrealizedPnl: 'Unrealized',
  },
  zh: {
    title: '模拟交易',
    balance: '账户余额',
    pnl: '累计盈亏',
    positions: '持仓',
    noPositions: '暂无持仓',
    orders: '交易记录',
    noOrders: '暂无交易记录',
    asset: '币种',
    quantity: '数量',
    entryPrice: '入场价',
    marketValue: '市值',
    side: '方向',
    price: '成交价',
    total: '金额',
    time: '时间',
    buy: '买入',
    sell: '卖出',
    loading: '加载中...',
    loginRequired: '请先登录后再使用模拟交易功能。',
    error: '数据加载失败',
    reasoning: '备注',
    winRate: '胜率',
    totalTrades: '总交易',
    lastUpdate: '最后更新',
    retry: '重试',
    portfolio: '投资组合',
    equityCurve: '权益曲线',
    pnlShort: '盈亏',
    usdt: 'USDT',
    openPositions: '当前持仓',
    recentOrders: '最近交易',
    unrealizedPnl: '浮动盈亏',
  },
}

/* ─── Equity Curve SVG Chart ──────────────────────── */

function EquityCurve({ orders, currentBalance }) {
  if (!orders || orders.length < 1) {
    return (
      <div className="tbot-chart-placeholder">
        <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
          <path d="M6 36 L16 24 L24 28 L34 12 L42 18" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round" strokeDasharray="4 4" opacity="0.4" />
        </svg>
        <span>No trade data yet</span>
      </div>
    )
  }

  const INITIAL = 10000
  const sorted = [...orders].sort((a, b) => new Date(a.created_at) - new Date(b.created_at))

  const points = [{ t: sorted[0].created_at, equity: INITIAL }]
  let bal = INITIAL
  for (const o of sorted) {
    if (o.side === 'buy') bal -= o.total_usdt
    else bal += o.total_usdt
    points.push({ t: o.created_at, equity: bal })
  }
  // Append current balance as final point
  points.push({ t: new Date().toISOString(), equity: currentBalance })

  const values = points.map(p => p.equity)
  const minVal = Math.min(...values) * 0.985
  const maxVal = Math.max(...values) * 1.015
  const range = maxVal - minVal || 1

  const W = 600, H = 180
  const pad = { top: 16, bottom: 28, left: 56, right: 16 }
  const cw = W - pad.left - pad.right
  const ch = H - pad.top - pad.bottom

  const xp = (i) => pad.left + (i / (points.length - 1)) * cw
  const yp = (v) => pad.top + ch - ((v - minVal) / range) * ch

  const line = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${xp(i).toFixed(1)},${yp(p.equity).toFixed(1)}`).join(' ')
  const area = line + ` L${xp(points.length - 1).toFixed(1)},${pad.top + ch} L${xp(0).toFixed(1)},${pad.top + ch} Z`

  const positive = currentBalance >= INITIAL
  const color = positive ? '#4ade80' : '#f87171'

  const yTicks = 5
  const yStep = range / yTicks

  const fmt = (v) => v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(0)
  const fmtDate = (iso) => {
    const d = new Date(iso)
    return `${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')}`
  }

  const labelIndices = []
  if (points.length > 1) {
    const step = Math.max(1, Math.floor((points.length - 1) / 4))
    for (let i = 0; i < points.length; i += step) labelIndices.push(i)
    if (labelIndices[labelIndices.length - 1] !== points.length - 1) labelIndices.push(points.length - 1)
  }

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="tbot-equity-svg" preserveAspectRatio="xMidYMid meet">
      <defs>
        <linearGradient id="eq-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.2" />
          <stop offset="100%" stopColor={color} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      {/* Grid */}
      {Array.from({ length: yTicks + 1 }, (_, i) => {
        const y = pad.top + (i / yTicks) * ch
        return (
          <g key={i}>
            <line x1={pad.left} y1={y} x2={W - pad.right} y2={y} stroke="var(--border-soft)" strokeWidth="0.5" />
            <text x={pad.left - 6} y={y + 3} textAnchor="end" fill="var(--text-muted)" fontSize="9" fontFamily="monospace">
              {fmt(minVal + yStep * (yTicks - i))}
            </text>
          </g>
        )
      })}
      {/* Area */}
      <path d={area} fill="url(#eq-fill)" />
      {/* Line */}
      <path d={line} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      {/* Dots */}
      {points.map((p, i) => (
        <circle key={i} cx={xp(i)} cy={yp(p.equity)} r="2" fill={color} stroke="var(--bg-surface)" strokeWidth="1" />
      ))}
      {/* X labels */}
      {labelIndices.map(i => (
        <text key={i} x={xp(i)} y={H - 4} textAnchor="middle" fill="var(--text-muted)" fontSize="9" fontFamily="monospace">
          {fmtDate(points[i].t)}
        </text>
      ))}
    </svg>
  )
}

/* ─── Metric Card ─────────────────────────────────── */

function MetricCard({ label, value, sub, positive, negative, icon }) {
  const cls = positive ? 'tbot-val-green' : negative ? 'tbot-val-red' : ''
  return (
    <div className="tbot-mcard">
      <div className="tbot-mcard-head">
        <span className="tbot-mcard-icon">{icon}</span>
        <span className="tbot-mcard-label">{label}</span>
      </div>
      <div className={`tbot-mcard-value ${cls}`}>{value}</div>
      {sub && <div className="tbot-mcard-sub">{sub}</div>}
    </div>
  )
}

/* ─── Position Card ───────────────────────────────── */

function PositionCard({ p, copy }) {
  const cost = p.entry_price * p.quantity
  const upnl = p.current_value_usdt - cost
  const pct = cost > 0 ? (upnl / cost) * 100 : 0
  const pos = upnl >= 0
  return (
    <div className="tbot-pos-card">
      <div className="tbot-pos-head">
        <span className="tbot-pos-sym">{p.asset_symbol}</span>
        <span className={`tbot-pos-pnl ${pos ? 'tbot-val-green' : 'tbot-val-red'}`}>
          {pos ? '+' : ''}{upnl.toFixed(2)}
        </span>
      </div>
      <div className="tbot-pos-detail">
        <div className="tbot-pos-row">
          <span>{copy.quantity}</span>
          <span>{p.quantity}</span>
        </div>
        <div className="tbot-pos-row">
          <span>{copy.entryPrice}</span>
          <span>${p.entry_price?.toFixed(2)}</span>
        </div>
        <div className="tbot-pos-row">
          <span>{copy.marketValue}</span>
          <span>${p.current_value_usdt?.toFixed(2)}</span>
        </div>
        <div className="tbot-pos-row">
          <span>{copy.pnlShort}</span>
          <span className={pos ? 'tbot-val-green' : 'tbot-val-red'}>{pos ? '+' : ''}{pct.toFixed(1)}%</span>
        </div>
      </div>
    </div>
  )
}

/* ─── Loading Skeletons ───────────────────────────── */

function LoadingSkeleton() {
  return (
    <div className="tbot-view">
      <div className="tbot-sk-grid">
        {[1, 2, 3, 4, 5].map(i => (
          <div key={i} className="tbot-sk-card">
            <div className="tbot-sk-line tbot-sk-short" />
            <div className="tbot-sk-line tbot-sk-med" />
            <div className="tbot-sk-line tbot-sk-tiny" />
          </div>
        ))}
      </div>
      <div className="tbot-sk-chart">
        <div className="tbot-sk-line tbot-sk-long" />
        <div className="tbot-sk-line tbot-sk-long" style={{ width: '70%', marginTop: 12 }} />
      </div>
    </div>
  )
}

/* ─── Main Component ──────────────────────────────── */

export default function TbotView({ apiBase, language }) {
  const copy = COPY[language] || COPY.en
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [lastUpdated, setLastUpdated] = useState(null)

  const authHeaders = useMemo(() => {
    const h = { 'Content-Type': 'application/json' }
    const t = typeof window !== 'undefined' ? window.localStorage.getItem('elephant_auth_token') : null
    if (t) h['Authorization'] = `Bearer ${t}`
    return h
  }, [])

  const loggedIn = Boolean(
    typeof window !== 'undefined' && window.localStorage.getItem('elephant_auth_token')
  )

  const fetchData = useCallback(async () => {
    if (!loggedIn) { setLoading(false); return }
    try {
      setError('')
      const res = await fetch(`${apiBase}/tbot/data`, { headers: authHeaders })
      if (!res.ok) {
        if (res.status === 401) { setError('loginRequired'); setLoading(false); return }
        throw new Error(String(res.status))
      }
      const json = await res.json()
      setData(json)
      setLastUpdated(new Date())
      setError('')
    } catch {
      setError('error')
    } finally {
      setLoading(false)
    }
  }, [apiBase, authHeaders, loggedIn])

  useEffect(() => { fetchData(); const id = setInterval(fetchData, 15000); return () => clearInterval(id) }, [fetchData])

  /* compute metrics */
  const metrics = useMemo(() => {
    if (!data) return null
    const { orders = [], account } = data
    const totalTrades = orders.length

    let wins = 0, closed = 0
    if (orders.length > 1) {
      const byAsset = {}
      for (const o of orders) {
        if (!byAsset[o.asset_symbol]) byAsset[o.asset_symbol] = []
        byAsset[o.asset_symbol].push(o)
      }
      for (const sym of Object.keys(byAsset)) {
        const list = byAsset[sym].sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
        let q = 0, cost = 0
        for (const o of list) {
          if (o.side === 'buy') { q += o.quantity; cost += o.total_usdt }
          else if (o.side === 'sell' && q > 0) {
            closed++
            if (o.price > cost / q) wins++
            const ratio = o.quantity / q
            cost *= (1 - ratio); q -= o.quantity
          }
        }
      }
    }

    const pnl = account?.total_pnl ?? 0
    return {
      balance: account?.balance_usdt ?? 0,
      totalPnl: pnl,
      pnlPct: (pnl / 10000) * 100,
      posCount: account?.position_count ?? 0,
      totalTrades,
      winRate: closed > 0 ? (wins / closed) * 100 : null,
      wins, closed,
    }
  }, [data])

  const fmtDT = (iso) => {
    if (!iso) return ''
    const d = new Date(iso)
    return `${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  }
  const fmtT = (iso) => {
    if (!iso) return ''
    const d = new Date(iso)
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  }

  /* states */
  if (!loggedIn) {
    return (
      <div className="workspace-view active">
        <div className="tbot-view">
          <div className="tbot-state-center">
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
              <rect x="8" y="18" width="32" height="24" rx="4" stroke="var(--text-muted)" strokeWidth="2" fill="none" />
              <path d="M16 18V14a8 8 0 0 1 16 0v4" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round" />
              <circle cx="24" cy="30" r="3" fill="var(--accent)" />
            </svg>
            <p>{copy.loginRequired}</p>
          </div>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="workspace-view active">
        <LoadingSkeleton />
      </div>
    )
  }

  if (error && !data) {
    return (
      <div className="workspace-view active">
        <div className="tbot-view">
          <div className="tbot-state-center">
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
              <circle cx="24" cy="24" r="18" stroke="var(--text-muted)" strokeWidth="2" fill="none" />
              <path d="M24 16v10" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" />
              <circle cx="24" cy="33" r="2" fill="var(--accent)" />
            </svg>
            <p>{copy.error}</p>
            <button className="tbot-retry-btn" onClick={fetchData}>{copy.retry}</button>
          </div>
        </div>
      </div>
    )
  }

  const positions = data?.positions ?? []
  const orders = data?.orders ?? []

  return (
    <div className="workspace-view active">
      <div className="tbot-view">
        {/* Header */}
        <div className="tbot-header">
          <div className="tbot-header-left">
            <h2 className="tbot-title">{copy.title}</h2>
            {lastUpdated && (
              <span className="tbot-header-ts">{copy.lastUpdate} {fmtDT(lastUpdated.toISOString())}</span>
            )}
          </div>
          <button className="tbot-refresh-btn" onClick={fetchData} title="Refresh">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M2 8a6 6 0 0 1 10.47-4M14 8a6 6 0 0 1-10.47 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              <path d="M12.5 1.5V4.5H9.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M3.5 14.5V11.5H6.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>

        {/* Metric Cards */}
        <div className="tbot-mcard-grid">
          <MetricCard
            label={copy.balance}
            value={`$${metrics?.balance?.toFixed(2) ?? '0.00'}`}
            sub={copy.usdt}
            icon={<svg width="18" height="18" viewBox="0 0 18 18" fill="none"><rect x="3" y="7" width="12" height="8" rx="2" stroke="currentColor" strokeWidth="1.2"/><path d="M6 7V5a3 3 0 0 1 6 0v2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>}
          />
          <MetricCard
            label={copy.pnlShort}
            value={`${(metrics?.totalPnl ?? 0) >= 0 ? '+' : ''}$${metrics?.totalPnl?.toFixed(2) ?? '0.00'}`}
            sub={`${(metrics?.pnlPct ?? 0) >= 0 ? '+' : ''}${metrics?.pnlPct?.toFixed(2) ?? '0.00'}%`}
            positive={(metrics?.totalPnl ?? 0) >= 0}
            negative={(metrics?.totalPnl ?? 0) < 0}
            icon={<svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M9 3v12M5 11l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>}
          />
          <MetricCard
            label={copy.winRate}
            value={metrics?.winRate != null ? `${metrics.winRate.toFixed(1)}%` : '—'}
            sub={metrics?.winRate != null ? `${metrics.wins}/${metrics.closed}` : copy.noOrders}
            positive={(metrics?.winRate ?? 0) >= 50}
            negative={(metrics?.winRate ?? 0) < 50 && metrics?.winRate != null}
            icon={<svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M4 14L7 8l4 2 3-6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>}
          />
          <MetricCard
            label={copy.positions}
            value={metrics?.posCount ?? 0}
            sub={copy.openPositions}
            icon={<svg width="18" height="18" viewBox="0 0 18 18" fill="none"><rect x="3" y="4" width="12" height="10" rx="2" stroke="currentColor" strokeWidth="1.2"/><path d="M7 8h4M7 11h4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>}
          />
          <MetricCard
            label={copy.totalTrades}
            value={metrics?.totalTrades ?? 0}
            sub={copy.orders}
            icon={<svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M3 5h12M3 9h12M3 13h8" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>}
          />
        </div>

        {/* Equity Curve */}
        <div className="tbot-section">
          <div className="tbot-section-head">
            <h3 className="tbot-section-title">{copy.equityCurve}</h3>
          </div>
          <div className="tbot-chart-card">
            <EquityCurve orders={orders} currentBalance={metrics?.balance ?? 0} />
          </div>
        </div>

        {/* Positions */}
        <div className="tbot-section">
          <div className="tbot-section-head">
            <h3 className="tbot-section-title">{copy.openPositions}</h3>
            {positions.length > 0 && <span className="tbot-badge-count">{positions.length}</span>}
          </div>
          {positions.length > 0 ? (
            <div className="tbot-pos-grid">
              {positions.map((p, i) => <PositionCard key={i} p={p} copy={copy} />)}
            </div>
          ) : (
            <div className="tbot-state-center tbot-state-sm">
              <svg width="28" height="28" viewBox="0 0 28 28" fill="none"><rect x="5" y="9" width="18" height="12" rx="3" stroke="var(--text-muted)" strokeWidth="1.5" fill="none"/><path d="M10 9V7a4 4 0 0 1 8 0v2" stroke="var(--text-muted)" strokeWidth="1.5" strokeLinecap="round"/></svg>
              <span>{copy.noPositions}</span>
            </div>
          )}
        </div>

        {/* Orders */}
        <div className="tbot-section">
          <div className="tbot-section-head">
            <h3 className="tbot-section-title">{copy.orders}</h3>
            {orders.length > 0 && <span className="tbot-badge-count">{orders.length}</span>}
          </div>
          {orders.length > 0 ? (
            <div className="tbot-table-wrap">
              <table className="tbot-table">
                <thead>
                  <tr>
                    <th>{copy.time}</th>
                    <th>{copy.side}</th>
                    <th>{copy.asset}</th>
                    <th>{copy.quantity}</th>
                    <th>{copy.price}</th>
                    <th>{copy.total}</th>
                    <th>{copy.reasoning}</th>
                  </tr>
                </thead>
                <tbody>
                  {[...orders].reverse().map(o => (
                    <tr key={o.id}>
                      <td className="tbot-cell-mono">{fmtT(o.created_at)}</td>
                      <td><span className={`tbot-badge-side ${o.side === 'buy' ? 'tbot-badge-buy' : 'tbot-badge-sell'}`}>{o.side === 'buy' ? copy.buy : copy.sell}</span></td>
                      <td><span className="tbot-cell-sym">{o.asset_symbol}</span></td>
                      <td className="tbot-cell-num">{o.quantity}</td>
                      <td className="tbot-cell-num">${o.price?.toFixed(2)}</td>
                      <td className="tbot-cell-num">${o.total_usdt?.toFixed(2)}</td>
                      <td className="tbot-cell-notes">{o.reasoning || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="tbot-state-center tbot-state-sm">
              <svg width="28" height="28" viewBox="0 0 28 28" fill="none"><path d="M4 7h20v14H4V7z" stroke="var(--text-muted)" strokeWidth="1.5" fill="none"/><path d="M4 11h20" stroke="var(--text-muted)" strokeWidth="1.5"/></svg>
              <span>{copy.noOrders}</span>
            </div>
          )}
        </div>

        {/* Error banner */}
        {error ? (
          <div className="tbot-err-banner">
            <span>{copy[error] || copy.error}</span>
            <button className="tbot-retry-btn" onClick={fetchData}>{copy.retry}</button>
          </div>
        ) : null}
      </div>
    </div>
  )
}
