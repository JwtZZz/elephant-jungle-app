import { useEffect, useState } from 'react'

const TRENDING_CACHE_KEY = 'meme-trending-cache:v1'
const TRENDING_CACHE_TTL_MS = 5 * 60 * 1000
const TRENDING_REFRESH_MS = 60 * 1000

let trendingMemoryCache = []
let trendingMemoryTimestamp = 0
let trendingInflightPromise = null

const COPY = {
  en: {
    title: 'Token Launchpad',
    name: 'Name',
    symbol: 'Symbol',
    description: 'Description',
    twitter: 'Twitter',
    telegram: 'Telegram',
    website: 'Website',
    image: 'Token Image',
    imageHint: 'Click to upload or paste URL',
    mintWallet: 'Mint Wallet',
    signerWallet: 'Signer Wallet',
    buyAmount: 'Buy Amount',
    amountMode: 'Amount Mode',
    slippage: 'Slippage %',
    priorityFee: 'Priority Fee',
    pool: 'Pool',
    showName: 'Show Name',
    build: 'Build',
    save: 'Save',
    descriptionPlaceholder: 'Token story, angle, meme context.',
    imagePlaceholder: 'Image URL or path',
    mintPlaceholder: 'Mint keypair public key',
    signerPlaceholder: 'Funding wallet public key',
    percentage: '% of supply',
    trueLabel: 'True',
    falseLabel: 'False',
    trending: 'Trending',
    trendingCopy: 'Hot meme tokens on Solana — live from DexScreener.',
    loading: 'Fetching trending tokens...',
    empty: 'No trending data right now.',
    price: 'Price',
    volume: '24H Vol',
    txns: '24H Txns',
    buys: 'B',
    sells: 'S',
    viewOn: 'View',
    building: 'Creating token on Solana...',
    success: 'Token created!',
    error: 'Creation failed',
    viewExplorer: 'View on Solscan',
    copyAddress: 'Copy Address',
    copied: 'Copied!',
  },
  zh: {
    title: '代币发射台',
    name: '名称',
    symbol: '简称',
    description: '描述',
    twitter: 'Twitter',
    telegram: 'Telegram',
    website: '网站',
    image: '代币图片',
    imageHint: '点击上传或粘贴 URL',
    mintWallet: 'Mint 钱包',
    signerWallet: '签名钱包',
    buyAmount: '买入数量',
    amountMode: '数量模式',
    slippage: '滑点 %',
    priorityFee: '优先费',
    pool: '池子',
    showName: '显示名称',
    build: '生成',
    save: '保存',
    descriptionPlaceholder: '代币简介、角度和 meme 叙事。',
    imagePlaceholder: '图片 URL 或路径',
    mintPlaceholder: 'Mint 公钥',
    signerPlaceholder: '出资钱包公钥',
    percentage: '供应量百分比',
    trueLabel: '是',
    falseLabel: '否',
    trending: '热门币种',
    trendingCopy: 'Solana 上热门 meme 代币 — 来自 DexScreener 实时数据。',
    loading: '正在获取热门数据...',
    empty: '暂无热门数据。',
    price: '价格',
    volume: '24H交易量',
    txns: '24H交易',
    buys: '买',
    sells: '卖',
    viewOn: '查看',
    building: '正在 Solana 上创建代币...',
    success: '代币创建成功！',
    error: '创建失败',
    viewExplorer: '在 Solscan 查看',
    copyAddress: '复制地址',
    copied: '已复制！',
  },
}

function readTrendingCache() {
  if (trendingMemoryCache.length && (Date.now() - trendingMemoryTimestamp) <= TRENDING_CACHE_TTL_MS) {
    return trendingMemoryCache
  }
  if (typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(TRENDING_CACHE_KEY)
    if (!raw) return []
    const payload = JSON.parse(raw)
    const timestamp = Number(payload?.timestamp || 0)
    const tokens = Array.isArray(payload?.tokens) ? payload.tokens : []
    if (!timestamp || !tokens.length) return []
    if ((Date.now() - timestamp) > TRENDING_CACHE_TTL_MS) return []
    trendingMemoryCache = tokens
    trendingMemoryTimestamp = timestamp
    return tokens
  } catch {
    return []
  }
}

function writeTrendingCache(tokens) {
  if (typeof window === 'undefined' || !Array.isArray(tokens) || !tokens.length) return
  const now = Date.now()
  trendingMemoryCache = tokens
  trendingMemoryTimestamp = now
  try {
    window.localStorage.setItem(
      TRENDING_CACHE_KEY,
      JSON.stringify({ timestamp: now, tokens }),
    )
  } catch {
    // ignore cache write failures
  }
}

async function fetchTrendingTokens(apiBase, { force = false } = {}) {
  const cachedTokens = readTrendingCache()
  if (!force && cachedTokens.length) {
    return cachedTokens
  }

  if (trendingInflightPromise) {
    return trendingInflightPromise
  }

  trendingInflightPromise = (async () => {
    const resp = await fetch(`${apiBase}/meme/trending`)
    if (!resp.ok) throw new Error(`trending failed (${resp.status})`)
    const payload = await resp.json()
    const tokens = Array.isArray(payload?.tokens) ? payload.tokens : []
    if (tokens.length) {
      writeTrendingCache(tokens)
    }
    return tokens
  })()

  try {
    return await trendingInflightPromise
  } finally {
    trendingInflightPromise = null
  }
}

export function warmTrendingCache(apiBase) {
  if (!apiBase) return Promise.resolve(readTrendingCache())
  return fetchTrendingTokens(apiBase).catch(() => readTrendingCache())
}

export default function AgentsView({ apiBase, language }) {
  const copy = COPY[language] || COPY.en
  const cachedTokens = readTrendingCache()
  const [tokens, setTokens] = useState(() => cachedTokens)
  const [loading, setLoading] = useState(() => !cachedTokens.length)

  // ── Form state ────────────────────────────────────────────────────────
  const [form, setForm] = useState({
    name: '',
    symbol: '',
    description: '',
    twitter: '',
    telegram: '',
    website: '',
    image_url: '',
    mintWallet: '',
    signerWallet: '',
    buyAmount: '0.01',
    amountMode: 'sol',
    slippage: '20',
    priorityFee: '0.0001',
    pool: 'pump',
    showName: true,
  })

  const [status, setStatus] = useState('idle') // idle | building | success | error
  const [result, setResult] = useState(null)
  const [errorMsg, setErrorMsg] = useState('')
  const [copied, setCopied] = useState(false)

  const setField = (field) => (e) => {
    const value = e.target.type === 'checkbox' ? e.target.checked : e.target.value
    setForm((prev) => ({ ...prev, [field]: value }))
    if (status === 'success' || status === 'error') {
      setStatus('idle')
      setResult(null)
      setErrorMsg('')
    }
  }

  const toggleShowName = (value) => {
    setForm((prev) => ({ ...prev, showName: value }))
  }

  const handleBuild = async () => {
    if (!form.name.trim() || !form.symbol.trim()) return

    setStatus('building')
    setResult(null)
    setErrorMsg('')

    try {
      const resp = await fetch(`${apiBase}/meme/create-token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: form.name.trim(),
          symbol: form.symbol.trim().toUpperCase(),
          description: form.description.trim(),
          image_url: form.image_url.trim(),
          twitter: form.twitter.trim(),
          telegram: form.telegram.trim(),
          website: form.website.trim(),
          buy_amount: parseFloat(form.buyAmount) || 0,
          slippage: parseFloat(form.slippage) || 20,
        }),
      })

      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'Token creation failed')

      setStatus('success')
      setResult(data)
    } catch (err) {
      setStatus('error')
      setErrorMsg(err.message || 'Unknown error')
    }
  }

  const handleCopyAddress = async (address) => {
    try {
      await navigator.clipboard.writeText(address)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // ignore
    }
  }

  // ── Trending tokens ───────────────────────────────────────────────────
  useEffect(() => {
    let ignore = false
    const localCachedTokens = readTrendingCache()

    if (localCachedTokens.length) {
      setTokens(localCachedTokens)
      setLoading(false)
    }

    const load = async (force = false) => {
      try {
        const nextTokens = await fetchTrendingTokens(apiBase, { force: force || !localCachedTokens.length })
        if (!ignore && Array.isArray(nextTokens) && nextTokens.length) {
          setTokens(nextTokens)
        }
      } catch (err) {
        console.error('Meme trending fallback', err)
      } finally {
        if (!ignore) setLoading(false)
      }
    }
    load()
    const timer = window.setInterval(() => load(true), TRENDING_REFRESH_MS)
    return () => {
      ignore = true
      window.clearInterval(timer)
    }
  }, [apiBase])

  return (
    <div className="workspace-view active agents-launch-view">
      <div className="meme-split">
        {/* ── Left: Launch Form ── */}
        <div className="meme-left">
          <div className="launch-builder-head launch-builder-head-simple">
            <div>
              <h2 className="launch-builder-title">{copy.title}</h2>
            </div>
          </div>

          <section className="launch-form-card launch-form-card-compact">
            <div className="launch-image-placeholder">
              <div className="launch-image-drop">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h10" /><path d="M8.5 10.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z" /><path d="m21 15-5-5L5 21" /><path d="M17 3v6" /><path d="M14 6h6" /></svg>
                <span>{copy.imageHint}</span>
              </div>
              <input
                type="text"
                className="launch-image-input"
                placeholder={copy.imagePlaceholder}
                value={form.image_url}
                onChange={setField('image_url')}
              />
            </div>

            <div className="launch-form-grid">
              <label className="launch-input-group">
                <span>{copy.name}</span>
                <input type="text" value={form.name} onChange={setField('name')} />
              </label>
              <label className="launch-input-group">
                <span>{copy.symbol}</span>
                <input type="text" value={form.symbol} onChange={setField('symbol')} />
              </label>
              <label className="launch-input-group launch-input-group-wide">
                <span>{copy.description}</span>
                <textarea rows="3" value={form.description} onChange={setField('description')} placeholder={copy.descriptionPlaceholder} />
              </label>
              <label className="launch-input-group">
                <span>{copy.twitter}</span>
                <input type="text" value={form.twitter} onChange={setField('twitter')} />
              </label>
              <label className="launch-input-group">
                <span>{copy.telegram}</span>
                <input type="text" value={form.telegram} onChange={setField('telegram')} />
              </label>
              <label className="launch-input-group">
                <span>{copy.website}</span>
                <input type="text" value={form.website} onChange={setField('website')} />
              </label>
              <label className="launch-input-group">
                <span>{copy.mintWallet}</span>
                <input type="text" value={form.mintWallet} onChange={setField('mintWallet')} placeholder={copy.mintPlaceholder} />
              </label>
              <label className="launch-input-group">
                <span>{copy.signerWallet}</span>
                <input type="text" value={form.signerWallet} onChange={setField('signerWallet')} placeholder={copy.signerPlaceholder} />
              </label>
              <label className="launch-input-group">
                <span>{copy.buyAmount}</span>
                <input type="text" value={form.buyAmount} onChange={setField('buyAmount')} />
              </label>
              <label className="launch-input-group">
                <span>{copy.amountMode}</span>
                <select value={form.amountMode} onChange={setField('amountMode')}>
                  <option value="sol">SOL</option>
                  <option value="percentage">{copy.percentage}</option>
                </select>
              </label>
              <label className="launch-input-group">
                <span>{copy.slippage}</span>
                <input type="text" value={form.slippage} onChange={setField('slippage')} />
              </label>
              <label className="launch-input-group">
                <span>{copy.priorityFee}</span>
                <input type="text" value={form.priorityFee} onChange={setField('priorityFee')} />
              </label>
              <label className="launch-input-group">
                <span>{copy.pool}</span>
                <select value={form.pool} onChange={setField('pool')}>
                  <option value="pump">pump</option>
                </select>
              </label>
              <label className="launch-input-group launch-toggle-group">
                <span>{copy.showName}</span>
                <div className="launch-toggle-row">
                  <button
                    type="button"
                    className={`launch-toggle ${form.showName ? 'active' : ''}`}
                    onClick={() => toggleShowName(true)}
                  >{copy.trueLabel}</button>
                  <button
                    type="button"
                    className={`launch-toggle ${!form.showName ? 'active' : ''}`}
                    onClick={() => toggleShowName(false)}
                  >{copy.falseLabel}</button>
                </div>
              </label>
            </div>

            {/* Status messages */}
            {status === 'building' ? (
              <div className="launch-status launch-status-building">
                <span className="launch-spinner" />
                {copy.building}
              </div>
            ) : null}

            {status === 'success' && result ? (
              <div className="launch-status launch-status-success">
                <strong>{copy.success}</strong>
                <div className="launch-result-row">
                  <span className="launch-result-label">Mint:</span>
                  <code className="launch-result-address">{result.mint_address}</code>
                  <button
                    type="button"
                    className="launch-copy-btn"
                    onClick={() => handleCopyAddress(result.mint_address)}
                  >{copied ? copy.copied : copy.copyAddress}</button>
                </div>
                <div className="launch-result-row">
                  <a
                    href={`https://solscan.io/token/${result.mint_address}`}
                    target="_blank"
                    rel="noreferrer"
                    className="launch-explorer-link"
                  >{copy.viewExplorer}</a>
                </div>
              </div>
            ) : null}

            {status === 'error' ? (
              <div className="launch-status launch-status-error">
                <strong>{copy.error}</strong>
                <p>{errorMsg}</p>
              </div>
            ) : null}

            <div className="launch-action-row">
              <button
                type="button"
                className="launch-primary-btn"
                disabled={status === 'building' || !form.name.trim() || !form.symbol.trim()}
                onClick={handleBuild}
              >{status === 'building' ? copy.building : copy.build}</button>
              <button type="button" className="launch-secondary-btn">{copy.save}</button>
            </div>
          </section>
        </div>

        {/* ── Right: Trending Tokens ── */}
        <div className="meme-right">
          <div className="meme-trending-header">
            <div className="agent-kicker">{copy.trending}</div>
            <p className="meme-trending-copy">{copy.trendingCopy}</p>
          </div>

          <div className="meme-trending-list">
            {loading ? (
              <div className="meme-trending-empty">{copy.loading}</div>
            ) : !tokens.length ? (
              <div className="meme-trending-empty">{copy.empty}</div>
            ) : (
              tokens.map((token) => {
                const up = Number(token.change24h) >= 0
                const buyRatio = token.buys24h + token.sells24h > 0
                  ? Math.round((token.buys24h / (token.buys24h + token.sells24h)) * 100)
                  : 50
                return (
                  <a
                    key={token.address}
                    className="meme-token-card"
                    href={token.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <div className="meme-token-top">
                      <span className="meme-token-icon">
                        <img
                          src={`https://dd.dexscreener.com/ds-data/tokens/solana/${token.address}.png?size=sm`}
                          alt=""
                          onError={(e) => { e.target.style.display = 'none' }}
                        />
                        <span className="meme-token-icon-fallback">{token.symbol?.slice(0, 2)}</span>
                      </span>
                      <div className="meme-token-info">
                        <div className="meme-token-symbol">{token.symbol}</div>
                        <div className="meme-token-name">{token.name}</div>
                      </div>
                      <div className={`meme-token-change ${up ? 'up' : 'down'}`}>
                        {up ? '+' : ''}{token.change24h}%
                      </div>
                    </div>

                    <div className="meme-token-stats">
                      <div className="meme-token-stat">
                        <span className="meme-token-label">{copy.price}</span>
                        <span className="meme-token-value">{token.price}</span>
                      </div>
                      <div className="meme-token-stat">
                        <span className="meme-token-label">{copy.volume}</span>
                        <span className="meme-token-value">{token.volume24h}</span>
                      </div>
                      <div className="meme-token-stat">
                        <span className="meme-token-label">{copy.txns}</span>
                        <span className="meme-token-value">
                          <span className="txn-buys">{copy.buys}{token.buys24h}</span>
                          <span className="txn-sep">/</span>
                          <span className="txn-sells">{copy.sells}{token.sells24h}</span>
                        </span>
                      </div>
                    </div>

                    <div className="meme-token-bar-track">
                      <span
                        className="meme-token-bar-fill"
                        style={{ width: `${buyRatio}%` }}
                      />
                    </div>
                  </a>
                )
              })
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
