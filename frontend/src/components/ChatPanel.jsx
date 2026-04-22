import { useEffect, useMemo, useRef, useState } from 'react'
import { useSpriteOrbit } from '../hooks/useSpriteOrbit'

const REQUEST_TIMEOUT_MS = 90000

const COPY = {
  en: {
    welcome: "Hello, I'm your Elephant Jungle assistant. What can I help you with?",
    copy: 'Copy',
    copied: 'Copied',
    retry: 'Retry',
    thinkingFrames: ['T', 'Th', 'Thi', 'Thin', 'Think', 'Thinki', 'Thinkin', 'Thinking', 'Thinking.', 'Thinking..', 'Thinking...'],
    placeholder: 'Ask something...',
    send: 'Send',
    requestFailed: 'request failed',
    noAnswer: 'No answer returned.',
    timeout: 'Request timed out, please retry.',
    backendError: 'Backend error',
  },
  zh: {
    welcome: "Hello, I'm your Elephant Jungle assistant. 你好，请问需要什么帮助？",
    copy: '复制',
    copied: '已复制',
    retry: '重试',
    thinkingFrames: ['想', '想一', '想一下', '想一下.', '想一下..', '想一下...'],
    placeholder: '想问什么...',
    send: '发送',
    requestFailed: '请求失败',
    noAnswer: '没有返回内容。',
    timeout: '请求超时，请重试。',
    backendError: '后端错误',
  },
}

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

function MessageActions({ copyLabel, copiedLabel, query, onRetry, retryLabel, text }) {
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
        <span className="msg-action-label">{copied ? copiedLabel : copyLabel}</span>
      </button>
      <button className="msg-action-btn" type="button" onClick={() => onRetry(query)}>
        {createRetryIcon()}
        <span className="msg-action-label">{retryLabel}</span>
      </button>
    </div>
  )
}

export default function ChatPanel({ apiBase, language }) {
  const copy = COPY[language] || COPY.en
  const [messages, setMessages] = useState([])
  const [inputValue, setInputValue] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const chatBoxRef = useRef(null)
  const chatSpriteTrackRef = useRef(null)
  const chatSpriteShellRef = useRef(null)
  const inputSpriteTrackRef = useRef(null)
  const inputSpriteShellRef = useRef(null)
  const welcomeStartedRef = useRef(false)
  const stopThinkingRef = useRef(null)
  const activeRequestRef = useRef(null)
  const activeRunIdRef = useRef(0)
  const activeBotIdRef = useRef(null)

  const { spriteMode, boost, cruise } = useSpriteOrbit([
    { trackRef: chatSpriteTrackRef, shellRef: chatSpriteShellRef, direction: 1 },
    { trackRef: inputSpriteTrackRef, shellRef: inputSpriteShellRef, direction: -1 },
  ])

  const frames = useMemo(() => copy.thinkingFrames, [copy.thinkingFrames])
  const frameDelays = useMemo(() => [55, 65, 75, 85, 95, 110, 125, 145, 175, 210, 250], [])

  const scrollToBottom = () => {
    window.requestAnimationFrame(() => {
      if (chatBoxRef.current) {
        chatBoxRef.current.scrollTop = chatBoxRef.current.scrollHeight
      }
    })
  }

  const askBackend = async (query, controller) => {
    let didTimeout = false
    const timeoutId = window.setTimeout(() => {
      didTimeout = true
      controller.abort()
    }, REQUEST_TIMEOUT_MS)
    try {
      const response = await fetch(`${apiBase}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, top_k: 5 }),
        signal: controller.signal,
      })
      if (!response.ok) {
        let detail = copy.requestFailed
        try {
          const payload = await response.json()
          detail = payload.detail || detail
        } catch {
          detail = `${detail} (${response.status})`
        }
        throw new Error(detail)
      }
      const payload = await response.json()
      return payload.answer || copy.noAnswer
    } catch (error) {
      if (error.name === 'AbortError') {
        if (didTimeout) {
          throw new Error(copy.timeout)
        }
        throw error
      }
      throw error
    } finally {
      window.clearTimeout(timeoutId)
    }
  }

  const streamAssistantText = (messageId, text, query, runId, options = {}) =>
    new Promise((resolve) => {
      const { hideActions = false } = options
      let index = 0
      const tick = () => {
        if (typeof runId === 'number' && runId !== activeRunIdRef.current) {
          resolve(false)
          return
        }
        index += 1
        setMessages((prev) =>
          prev.map((message) =>
            message.id === messageId
              ? {
                  ...message,
                  text: text.slice(0, index),
                  thinking: false,
                  hideActions,
                  hiddenWhilePending: false,
                  query,
                }
              : message,
          ),
        )
        scrollToBottom()
        if (index < text.length) {
          window.setTimeout(tick, 38)
        } else {
          resolve(true)
        }
      }
      window.setTimeout(tick, 180)
    })

  useEffect(() => {
    const welcomeId = 'bot-welcome'

    if (!welcomeStartedRef.current) {
      welcomeStartedRef.current = true
      setMessages([{ id: welcomeId, role: 'bot', text: '', query: '', hideActions: true }])
      scrollToBottom()
      streamAssistantText(welcomeId, copy.welcome, '', undefined, { hideActions: true })
      return
    }

    setMessages((prev) => {
      if (prev.length === 1 && prev[0]?.id === welcomeId) {
        return [{ ...prev[0], text: copy.welcome, query: '' }]
      }
      return prev
    })
  }, [copy.welcome])

  const runThinking = (messageId) => {
    let index = 0
    let stopped = false
    const tick = () => {
      if (stopped) return
      setMessages((prev) =>
        prev.map((message) => (message.id === messageId ? { ...message, text: frames[index], thinking: true } : message)),
      )
      scrollToBottom()
      const delay = frameDelays[index % frameDelays.length]
      index = (index + 1) % frames.length
      window.setTimeout(tick, delay)
    }
    tick()
    return () => {
      stopped = true
    }
  }

  const interruptActiveReply = () => {
    activeRunIdRef.current += 1
    if (activeRequestRef.current) {
      activeRequestRef.current.abort()
      activeRequestRef.current = null
    }
    if (typeof stopThinkingRef.current === 'function') {
      stopThinkingRef.current()
      stopThinkingRef.current = null
    }
    if (activeBotIdRef.current) {
      const interruptedBotId = activeBotIdRef.current
      setMessages((prev) =>
        prev.map((message) =>
          message.id === interruptedBotId
            ? { ...message, thinking: false, hideActions: true, hiddenWhilePending: true, text: '' }
            : message,
        ),
      )
      activeBotIdRef.current = null
    }
    setIsStreaming(false)
  }

  const sendQuery = async (query, retryMessageId = null) => {
    if (!query.trim()) return
    interruptActiveReply()
    setIsStreaming(true)
    boost()

    const userMessage = retryMessageId ? null : { id: `user-${Date.now()}`, role: 'user', text: query }
    const botId = retryMessageId || `bot-${Date.now()}`
    const controller = new AbortController()
    const runId = activeRunIdRef.current

    activeRequestRef.current = controller
    activeBotIdRef.current = botId

    setMessages((prev) => {
      const next = [...prev]
      if (userMessage) next.push(userMessage)
      if (retryMessageId) {
        return next.map((message) =>
          message.id === retryMessageId ? { ...message, text: frames[0], thinking: true } : message,
        )
      }
      next.push({ id: botId, role: 'bot', text: frames[0], thinking: true, query })
      return next
    })
    scrollToBottom()

    const stopThinking = runThinking(botId)
    stopThinkingRef.current = stopThinking

    try {
      const answer = await askBackend(query, controller)
      if (runId !== activeRunIdRef.current) return
      stopThinking()
      stopThinkingRef.current = null
      await streamAssistantText(botId, answer, query, runId)
    } catch (error) {
      if (error.name === 'AbortError') {
        return
      }
      if (runId !== activeRunIdRef.current) return
      stopThinking()
      stopThinkingRef.current = null
      await streamAssistantText(botId, `${copy.backendError}: ${error.message}`, query, runId)
    } finally {
      if (activeRequestRef.current === controller) {
        activeRequestRef.current = null
      }
      if (activeBotIdRef.current === botId && runId === activeRunIdRef.current) {
        activeBotIdRef.current = null
      }
      if (runId === activeRunIdRef.current) {
        cruise()
        setIsStreaming(false)
      }
    }
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
          {messages
            .filter((message) => !(message.hiddenWhilePending && !message.text.trim()))
            .map((message) => (
            <div className={`msg ${message.role} ${message.role === 'bot' ? 'assistant' : ''}`} key={message.id}>
              <div className={`msg-content ${message.thinking ? 'thinking-inline' : ''}`}>{message.text}</div>
              {message.role === 'bot' && !message.thinking && !message.hideActions && message.text.trim() ? (
                <MessageActions
                  copyLabel={copy.copy}
                  copiedLabel={copy.copied}
                  query={message.query}
                  retryLabel={copy.retry}
                  text={message.text}
                  onRetry={(query) => sendQuery(query, message.id)}
                />
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
            placeholder={copy.placeholder}
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
          />
        </div>
        <button
          className="send-button"
          type="button"
          onClick={() => {
            const query = inputValue
            setInputValue('')
            sendQuery(query)
          }}
        >
          {copy.send}
        </button>
      </div>
    </div>
  )
}
