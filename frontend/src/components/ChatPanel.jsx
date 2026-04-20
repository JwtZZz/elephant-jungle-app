import { useMemo, useRef, useState } from 'react'
import { useSpriteOrbit } from '../hooks/useSpriteOrbit'

const REQUEST_TIMEOUT_MS = 20000

function createCopyIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="9" y="9" width="10" height="10" rx="2" />
      <path d="M15 9V7a2 2 0 0 0-2-2H7a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2" />
    </svg>
  )
}

function createRetryIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M20 11a8 8 0 1 0 2.2 5.5" />
      <path d="M20 4v7h-7" />
    </svg>
  )
}

function MessageActions({ query, onRetry, text }) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 900)
    } catch (error) {
      console.error('Copy failed', error)
    }
  }

  return (
    <div className="msg-actions">
      <button className="msg-action-btn" type="button" onClick={copy}>
        {createCopyIcon()}
        <span className="msg-action-label">{copied ? 'Copied' : 'Copy'}</span>
      </button>
      <button className="msg-action-btn" type="button" onClick={() => onRetry(query)}>
        {createRetryIcon()}
        <span className="msg-action-label">Retry</span>
      </button>
    </div>
  )
}

export default function ChatPanel({ apiBase, theme }) {
  const [messages, setMessages] = useState([])
  const [inputValue, setInputValue] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const chatBoxRef = useRef(null)
  const chatSpriteTrackRef = useRef(null)
  const chatSpriteShellRef = useRef(null)
  const inputSpriteTrackRef = useRef(null)
  const inputSpriteShellRef = useRef(null)

  const { spriteMode, boost, cruise } = useSpriteOrbit([
    { trackRef: chatSpriteTrackRef, shellRef: chatSpriteShellRef, direction: 1 },
    { trackRef: inputSpriteTrackRef, shellRef: inputSpriteShellRef, direction: -1 },
  ])

  const frames = useMemo(() => ['T', 'Th', 'Thi', 'Thin', 'Think', 'Thinki', 'Thinkin', 'Thinking', 'Thinking.', 'Thinking..', 'Thinking...'], [])
  const frameDelays = useMemo(() => [55, 65, 75, 85, 95, 110, 125, 145, 175, 210, 250], [])

  const scrollToBottom = () => {
    window.requestAnimationFrame(() => {
      if (chatBoxRef.current) {
        chatBoxRef.current.scrollTop = chatBoxRef.current.scrollHeight
      }
    })
  }

  const askBackend = async (query) => {
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
    try {
      const response = await fetch(`${apiBase}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, top_k: 5 }),
        signal: controller.signal,
      })
      if (!response.ok) {
        let detail = 'request failed'
        try {
          const payload = await response.json()
          detail = payload.detail || detail
        } catch {
          detail = `${detail} (${response.status})`
        }
        throw new Error(detail)
      }
      const payload = await response.json()
      return payload.answer || 'No answer returned.'
    } catch (error) {
      if (error.name === 'AbortError') {
        throw new Error('Request timed out, please retry.')
      }
      throw error
    } finally {
      window.clearTimeout(timeoutId)
    }
  }

  const streamAssistantText = (messageId, text, query) =>
    new Promise((resolve) => {
      let index = 0
      const tick = () => {
        index += 1
        setMessages((prev) =>
          prev.map((message) =>
            message.id === messageId
              ? { ...message, text: text.slice(0, index), thinking: false, query }
              : message,
          ),
        )
        scrollToBottom()
        if (index < text.length) {
          window.setTimeout(tick, 38)
        } else {
          resolve()
        }
      }
      window.setTimeout(tick, 180)
    })

  const runThinking = (messageId) => {
    let index = 0
    let stopped = false
    const tick = () => {
      if (stopped) return
      setMessages((prev) =>
        prev.map((message) => (message.id === messageId ? { ...message, text: frames[index], thinking: true } : message)),
      )
      scrollToBottom()
      const delay = frameDelays[index]
      index = (index + 1) % frames.length
      window.setTimeout(tick, delay)
    }
    tick()
    return () => {
      stopped = true
    }
  }

  const sendQuery = async (query, retryMessageId = null) => {
    if (!query.trim() || isStreaming) return
    setIsStreaming(true)
    boost()

    const userMessage = retryMessageId
      ? null
      : { id: `user-${Date.now()}`, role: 'user', text: query }
    const botId = retryMessageId || `bot-${Date.now()}`

    setMessages((prev) => {
      const next = [...prev]
      if (userMessage) next.push(userMessage)
      if (retryMessageId) {
        return next.map((message) =>
          message.id === retryMessageId
            ? { ...message, text: 'Thinking...', thinking: true }
            : message,
        )
      }
      next.push({ id: botId, role: 'bot', text: 'Thinking...', thinking: true, query })
      return next
    })
    scrollToBottom()

    const stopThinking = runThinking(botId)

    try {
      const answer = await askBackend(query)
      stopThinking()
      await streamAssistantText(botId, answer, query)
    } catch (error) {
      stopThinking()
      await streamAssistantText(botId, `Backend error: ${error.message}`, query)
    }

    cruise()
    setIsStreaming(false)
  }

  return (
    <div className="right-panel">
      <div className="chat-stage">
        <div className="chat-sprite-track" ref={chatSpriteTrackRef} aria-hidden="true">
          <div className="sprite-shell facing-right" ref={chatSpriteShellRef}>
            <div className={`sprite-avatar ${spriteMode}`} />
          </div>
        </div>
        <div className="chat-box" ref={chatBoxRef}>
          {messages.map((message) => (
            <div className={`msg ${message.role} ${message.role === 'bot' ? 'assistant' : ''}`} key={message.id}>
              <div className={`msg-content ${message.thinking ? 'thinking-inline' : ''}`}>{message.text}</div>
              {message.role === 'bot' && !message.thinking ? (
                <MessageActions query={message.query} text={message.text} onRetry={(query) => sendQuery(query, message.id)} />
              ) : null}
            </div>
          ))}
        </div>
      </div>
      <div className="input-row">
        <div className="input-wrap">
          <div className="input-sprite-track" ref={inputSpriteTrackRef} aria-hidden="true">
            <div className="sprite-shell facing-left" ref={inputSpriteShellRef}>
              <div className={`sprite-avatar ${spriteMode}`} />
            </div>
          </div>
          <input
            type="text"
            value={inputValue}
            placeholder="问点什么..."
            onChange={(event) => {
              setInputValue(event.target.value)
              boost()
            }}
            onBlur={cruise}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                const query = inputValue
                setInputValue('')
                sendQuery(query)
              }
            }}
            disabled={isStreaming}
          />
        </div>
        <button
          className="send-button"
          type="button"
          disabled={isStreaming}
          onClick={() => {
            const query = inputValue
            setInputValue('')
            sendQuery(query)
          }}
        >
          Send
        </button>
      </div>
    </div>
  )
}
