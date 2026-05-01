import { useCallback, useEffect, useMemo, useState } from 'react'
import { fallbackBriefs, fallbackMarketRows } from '../data/fallbacks'

const MARKET_REFRESH_MS = 3000
const BRIEFS_REFRESH_MS = 5 * 60 * 60 * 1000

function getApiBase() {
  const hostname = window.location.hostname || '127.0.0.1'
  if (
    hostname === 'localhost' ||
    hostname === '127.0.0.1' ||
    hostname === '0.0.0.0'
  ) {
    return `${window.location.protocol}//${hostname}:8000`
  }
  if (hostname.endsWith('trycloudflare.com')) {
    return window.location.origin
  }
  return window.location.origin
}

export function useMarketData() {
  const apiBase = useMemo(() => getApiBase(), [])
  const [marketRows, setMarketRows] = useState(fallbackMarketRows)
  const [briefs, setBriefs] = useState(fallbackBriefs)

  const loadMarketData = useCallback(async () => {
    try {
      const response = await fetch(`${apiBase}/market/coins`)
      if (!response.ok) {
        throw new Error(`market request failed (${response.status})`)
      }
      const payload = await response.json()
      if (Array.isArray(payload.coins) && payload.coins.length) {
        setMarketRows(payload.coins)
      }
    } catch (error) {
      console.error('Market data fallback', error)
      setMarketRows(fallbackMarketRows)
    }
  }, [apiBase])

  const loadBriefs = useCallback(async () => {
    try {
      const response = await fetch(`${apiBase}/market/briefs`)
      if (!response.ok) {
        throw new Error(`briefs request failed (${response.status})`)
      }
      const payload = await response.json()
      setBriefs({
        social: Array.isArray(payload.social) ? payload.social : fallbackBriefs.social,
        news: Array.isArray(payload.news) ? payload.news : fallbackBriefs.news,
      })
    } catch (error) {
      console.error('Briefs fallback', error)
      setBriefs(fallbackBriefs)
    }
  }, [apiBase])

  useEffect(() => {
    loadMarketData()
    const timer = window.setInterval(loadMarketData, MARKET_REFRESH_MS)
    return () => window.clearInterval(timer)
  }, [loadMarketData])

  useEffect(() => {
    loadBriefs()
    const timer = window.setInterval(loadBriefs, BRIEFS_REFRESH_MS)
    return () => window.clearInterval(timer)
  }, [loadBriefs])

  return { apiBase, marketRows, briefs }
}
