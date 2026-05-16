import { useState, useEffect } from 'react'

const TYPE_MS = 18
const HOLD_MS = 1500

export function useAutoCycleBubble(language) {
  const snippets =
    language === 'zh'
      ? ['BTC新高', 'ETF流向', 'ETH动态', 'Meme热度']
      : ['BTC move', 'ETF flow', 'ETH watch', 'Meme heat']

  const [text, setText] = useState('')

  useEffect(() => {
    if (!snippets.length) {
      setText('')
      return undefined
    }

    let snippetIndex = 0
    let charIndex = 0
    let stopped = false

    const typeNext = () => {
      if (stopped) return
      const snippet = snippets[snippetIndex % snippets.length] || ''
      if (!snippet) return
      charIndex += 1
      setText(snippet.slice(0, charIndex))
      if (charIndex < snippet.length) {
        window.setTimeout(typeNext, TYPE_MS)
        return
      }
      window.setTimeout(() => {
        snippetIndex = (snippetIndex + 1) % snippets.length
        charIndex = 0
        setText('')
        window.setTimeout(typeNext, 100)
      }, HOLD_MS)
    }

    const startTimer = window.setTimeout(typeNext, 100)

    return () => {
      stopped = true
      window.clearTimeout(startTimer)
    }
  }, [language]) // eslint-disable-line react-hooks/exhaustive-deps

  return text
}
