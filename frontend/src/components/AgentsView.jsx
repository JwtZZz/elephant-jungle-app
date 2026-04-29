import { useEffect, useState } from 'react'

const TRENDING_CACHE_KEY = 'meme-trending-cache:v1'
const TRENDING_CACHE_TTL_MS = 5 * 60 * 1000
const TRENDING_REFRESH_MS = 60 * 1000

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
  },
}

function readTrendingCache() {
  if (typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(TRENDING_CACHE_KEY)
    if (!raw) return []
    const payload = JSON.parse(raw)
    const timestamp = Number(payload?.timestamp || 0)
    const tokens = Array.isArray(payload?.tokens) ? payload.tokens : []
    if (!timestamp || !tokens.length) return []
    if ((Date.now() - timestamp) > TRENDING_CACHE_TTL_MS) return []
    return tokens
  } catch {
    return []
  }
}

function writeTrendingCache(tokens) {
  if (typeof window === 'undefined' || !Array.isArray(tokens) || !tokens.length) return
  try {
    window.localStorage.setItem(
      TRENDING_CACHE_KEY,
      JSON.stringify({ timestamp: Date.now(), tokens }),
    )
  } catch {
    // ignore cache write failures
  }
}

export default function AgentsView({ apiBase, language }) {
  const copy = COPY[language] || COPY.en
  const [tokens, setTokens] = useState(() => readTrendingCache())
  const [loading, setLoading] = useState(() => !readTrendingCache().length)

  useEffect(() => {
    let ignore = false
    const cachedTokens = readTrendingCache()

    if (cachedTokens.length) {
      setTokens(cachedTokens)
      setLoading(false)
    }

    const load = async () => {
      try {
        const resp = await fetch(`${apiBase}/meme/trending`)
        if (!resp.ok) throw new Error(`trending failed (${resp.status})`)
        const payload = await resp.json()
        if (!ignore && Array.isArray(payload.tokens)) {
          setTokens(payload.tokens)
          writeTrendingCache(payload.tokens)
        }
      } catch (err) {
        console.error('Meme trending fallback', err)
      } finally {
        if (!ignore) setLoading(false)
      }
    }
    load()
    const timer = window.setInterval(load, TRENDING_REFRESH_MS)
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
            </div>
            <div className="launch-form-grid">
              <label className="launch-input-group">
                <span>{copy.name}</span>
                <input type="text" />
              </label>
              <label className="launch-input-group">
                <span>{copy.symbol}</span>
                <input type="text" />
              </label>
              <label className="launch-input-group launch-input-group-wide">
                <span>{copy.description}</span>
                <textarea rows="3" />
              </label>
              <label className="launch-input-group">
                <span>{copy.twitter}</span>
                <input type="text" />
              </label>
              <label className="launch-input-group">
                <span>{copy.telegram}</span>
                <input type="text" />
              </label>
              <label className="launch-input-group">
                <span>{copy.website}</span>
                <input type="text" />
              </label>
              <label className="launch-input-group">
                <span>{copy.mintWallet}</span>
                <input type="text" />
              </label>
              <label className="launch-input-group">
                <span>{copy.signerWallet}</span>
                <input type="text" />
              </label>
              <label className="launch-input-group">
                <span>{copy.buyAmount}</span>
                <input type="text" />
              </label>
              <label className="launch-input-group">
                <span>{copy.amountMode}</span>
                <select defaultValue="sol">
                  <option value="sol">SOL</option>
                  <option value="percentage">{copy.percentage}</option>
                </select>
              </label>
              <label className="launch-input-group">
                <span>{copy.slippage}</span>
                <input type="text" />
              </label>
              <label className="launch-input-group">
                <span>{copy.priorityFee}</span>
                <input type="text" />
              </label>
              <label className="launch-input-group">
                <span>{copy.pool}</span>
                <select defaultValue="pump">
                  <option value="pump">pump</option>
                </select>
              </label>
              <label className="launch-input-group launch-toggle-group">
                <span>{copy.showName}</span>
                <div className="launch-toggle-row">
                  <button type="button" className="launch-toggle active">{copy.trueLabel}</button>
                  <button type="button" className="launch-toggle">{copy.falseLabel}</button>
                </div>
              </label>
            </div>

            <div className="launch-action-row">
              <button type="button" className="launch-primary-btn">{copy.build}</button>
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
