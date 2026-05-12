import { useCallback, useEffect, useRef, useState } from 'react'

function cleanHeadlineTitle(title = '') {
  return String(title)
    .replace(/\s+/g, ' ')
    .replace(/\s+[|·-]\s+[^|·-]+$/, '')
    .trim()
}

export function useSpriteHoverNews(apiBase, index = 0) {
  const [bubbleText, setBubbleText] = useState('')
  const [isHovered, setIsHovered] = useState(false)
  const newsItemsRef = useRef([])
  const intervalRef = useRef(null)

  useEffect(() => {
    if (!apiBase) return
    let cancelled = false
    fetch(`${apiBase}/market/briefs`)
      .then((r) => (r.ok ? r.json() : null))
      .then((payload) => {
        if (cancelled || !payload) return
        const items = [...(payload?.social || []), ...(payload?.news || [])]
        newsItemsRef.current = items
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [apiBase])

  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [])

  const handleMouseEnter = useCallback(() => {
    setIsHovered(true)
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }

    const items = newsItemsRef.current
    if (!items.length) {
      setBubbleText('')
      return
    }

    const item = items[index % items.length]
    const text = cleanHeadlineTitle(item?.title || '')
    if (!text) {
      setBubbleText('')
      return
    }

    setBubbleText('')
    let i = 0
    intervalRef.current = setInterval(() => {
      i++
      if (i <= text.length) {
        setBubbleText(text.slice(0, i))
      } else {
        if (intervalRef.current) clearInterval(intervalRef.current)
      }
    }, 25)
  }, [index])

  const handleMouseLeave = useCallback(() => {
    setIsHovered(false)
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
    setBubbleText('')
  }, [])

  return { bubbleText, isHovered, handleMouseEnter, handleMouseLeave }
}
