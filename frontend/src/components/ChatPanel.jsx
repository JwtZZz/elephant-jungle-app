import { useEffect, useMemo, useRef, useState } from 'react'
import { useSpriteOrbit } from '../hooks/useSpriteOrbit'
import ThemeToggle from './ThemeToggle'

const REQUEST_TIMEOUT_MS = 90000

const COPY = {
  en: {
    welcome: "Hello, I'm your Elephant Jungle assistant. What can I help you with?",
    login: 'Login',
    register: 'Register',
    guest: 'Guest',
    copy: 'Copy',
    copied: 'Copied',
    retry: 'Retry',
    thinkingFrames: ['T', 'Th', 'Thi', 'Thin', 'Think', 'Thinki', 'Thinkin', 'Thinking', 'Thinking.', 'Thinking..', 'Thinking...'],
    placeholder: 'Ask something...',
    send: 'Send',
    requestFailed: 'Request failed',
    noAnswer: 'No answer returned.',
    timeout: 'Request timed out, please retry.',
    backendError: 'Backend error',
    imageOcr: 'Image OCR',
    imageAttached: 'Ready to send',
    ocrReading: 'Reading image...',
    ocrReady: 'OCR ready',
    ocrFailed: 'OCR failed',
    ocrNoText: 'No text found in image.',
  },
  zh: {
    welcome: "Hello, I'm your Elephant Jungle assistant. 你好，请问需要什么帮助？",
    login: 'Login',
    register: 'Regist',
    guest: 'Guest',
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
    imageOcr: '图片识别',
    imageAttached: '待发送',
    ocrReading: '正在识别图片...',
    ocrReady: '识别完成',
    ocrFailed: '识别失败',
    ocrNoText: '图片里没有识别到文字。',
  },
}

function CopyIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="9" y="9" width="10" height="10" rx="2" />
      <path d="M15 9V7a2 2 0 0 0-2-2H7a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2" />
    </svg>
  )
}

function RetryIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M20 11a8 8 0 1 0 2.2 5.5" />
      <path d="M20 4v7h-7" />
    </svg>
  )
}

function ImageIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M21 19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h10" />
      <path d="M8.5 10.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z" />
      <path d="m21 15-5-5L5 21" />
      <path d="M17 3v6" />
      <path d="M14 6h6" />
    </svg>
  )
}

function MessageActions({ copyLabel, copiedLabel, query, onRetry, retryLabel, text }) {
  const [copied, setCopied] = useState(false)

  const fallbackCopy = (value) => {
    const textarea = document.createElement('textarea')
    textarea.value = value
    textarea.setAttribute('readonly', '')
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    textarea.style.pointerEvents = 'none'
    document.body.appendChild(textarea)
    textarea.focus()
    textarea.select()
    const success = document.execCommand('copy')
    document.body.removeChild(textarea)
    return success
  }

  const copy = async () => {
    try {
      if (navigator.clipboard?.writeText && window.isSecureContext) {
        await navigator.clipboard.writeText(text)
      } else {
        const success = fallbackCopy(text)
        if (!success) throw new Error('fallback copy failed')
      }
      setCopied(true)
      window.setTimeout(() => setCopied(false), 900)
    } catch (error) {
      console.error('Copy failed', error)
    }
  }

  return (
    <div className="msg-actions">
      <button className="msg-action-btn" type="button" onClick={copy}>
        <CopyIcon />
        <span className="msg-action-label">{copied ? copiedLabel : copyLabel}</span>
      </button>
      <button className="msg-action-btn" type="button" onClick={() => onRetry(query)}>
        <RetryIcon />
        <span className="msg-action-label">{retryLabel}</span>
      </button>
    </div>
  )
}

export default function ChatPanel({ apiBase, theme, setTheme, language, setLanguage }) {
  const copy = COPY[language] || COPY.en
  const [accountEmail] = useState(() => {
    if (typeof window === 'undefined') return ''
    return window.localStorage.getItem('elephant_account_email') || ''
  })
  const [messages, setMessages] = useState([])
  const [inputValue, setInputValue] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [ocrState, setOcrState] = useState(null)
  const [selectedImageFile, setSelectedImageFile] = useState(null)
  const [selectedImagePreview, setSelectedImagePreview] = useState('')
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
  const fileInputRef = useRef(null)

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

  const askBackend = async (query, controller, options = {}) => {
    const { useRag = true } = options
    let didTimeout = false
    const timeoutId = window.setTimeout(() => {
      didTimeout = true
      controller.abort()
    }, REQUEST_TIMEOUT_MS)

    try {
      const response = await fetch(`${apiBase}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, top_k: 5, use_rag: useRag }),
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

  const readFileAsDataUrl = (file) =>
    new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result || ''))
      reader.onerror = () => reject(new Error(copy.requestFailed))
      reader.readAsDataURL(file)
    })

  const runImageOcr = async (file) => {
    if (!file) return ''
    boost()

    const imageDataUrl = await readFileAsDataUrl(file)

    const response = await fetch(`${apiBase}/ocr/image`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image_data_url: imageDataUrl,
        filename: file.name,
      }),
    })

    if (!response.ok) {
      let detail = copy.requestFailed
      try {
        const payload = await response.json()
        detail = payload.detail || detail
      } catch {
        detail = `${detail} (${response.status})`
      }
      const normalized = String(detail || '')
      if (
        normalized.includes('Bad OCR response') ||
        normalized.includes('OCR did not return readable text') ||
        normalized.includes("'choices'") ||
        normalized.includes('"choices"')
      ) {
        detail = copy.ocrNoText
      }
      throw new Error(detail)
    }

    const payload = await response.json()
    const extractedText = (payload.text || '').trim()
    if (!extractedText) {
      throw new Error(copy.ocrNoText)
    }
    return extractedText
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
    if (!query.trim() && !selectedImageFile) return
    interruptActiveReply()
    setIsStreaming(true)
    boost()

    const userText = query.trim()
    const userMessage = retryMessageId
      ? null
      : {
          id: `user-${Date.now()}`,
          role: 'user',
          text: userText,
          imageUrl: selectedImagePreview || '',
        }
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
      next.push({ id: botId, role: 'bot', text: frames[0], thinking: true, query: userText })
      return next
    })
    scrollToBottom()

    const stopThinking = runThinking(botId)
    stopThinkingRef.current = stopThinking

    try {
      let backendQuery = query
      let useRag = true
      if (selectedImageFile) {
        setOcrState({ name: selectedImageFile.name, status: 'loading' })
        const extractedText = await runImageOcr(selectedImageFile)
        setOcrState({ name: selectedImageFile.name, status: 'ready' })
        useRag = false
        backendQuery = query.trim()
          ? `${query.trim()}\n\n[Image OCR]\n${extractedText}`
          : `[Image OCR]\n${extractedText}`
      }

      const answer = await askBackend(backendQuery, controller, { useRag })
      if (runId !== activeRunIdRef.current) return
      stopThinking()
      stopThinkingRef.current = null
      await streamAssistantText(botId, answer, backendQuery, runId)
      setSelectedImageFile(null)
      setSelectedImagePreview('')
      setOcrState(null)
    } catch (error) {
      if (error.name === 'AbortError') {
        return
      }
      if (runId !== activeRunIdRef.current) return
      stopThinking()
      stopThinkingRef.current = null
      if (selectedImageFile) {
        setSelectedImageFile(null)
        setSelectedImagePreview('')
        setOcrState(null)
      }
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
    <div className="right-col">
      <div className="right-topbar">
        <div className="right-topbar-left">
          <div className="language-toggle" role="group" aria-label="Language toggle">
            <button
              type="button"
              className={`language-chip ${language === 'zh' ? 'active' : ''}`}
              onClick={() => setLanguage?.('zh')}
            >
              中文
            </button>
            <button
              type="button"
              className={`language-chip ${language === 'en' ? 'active' : ''}`}
              onClick={() => setLanguage?.('en')}
            >
              English
            </button>
          </div>
        </div>
        <div className="right-topbar-right">
          <ThemeToggle theme={theme} setTheme={setTheme} language={language} />
          <div className="account-chip" role="button" tabIndex={0}>
            <span className="account-chip-avatar" aria-hidden="true">
              {accountEmail ? accountEmail.slice(0, 1).toUpperCase() : 'E'}
            </span>
            <div className="account-chip-copy">
              {accountEmail ? (
                <span className="account-chip-email">{accountEmail}</span>
              ) : (
                <div className="account-chip-actions">
                  <span className="account-chip-action">{copy.login}</span>
                  <span className="account-chip-divider" aria-hidden="true" />
                  <span className="account-chip-action">{copy.register}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
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
                <div className={`msg-content ${message.thinking ? 'thinking-inline' : ''} ${message.imageUrl ? 'has-image' : ''}`}>
                  {message.imageUrl ? (
                    <img className="chat-image-preview" src={message.imageUrl} alt="uploaded content" />
                  ) : null}
                  {message.text ? <div>{message.text}</div> : null}
                </div>
                {message.role === 'bot' && !message.thinking && !message.hideActions && message.text.trim() ? (
                  <MessageActions
                    copyLabel={copy.copy}
                    copiedLabel={copy.copied}
                    query={message.query}
                    retryLabel={copy.retry}
                    text={message.text}
                    onRetry={(nextQuery) => sendQuery(nextQuery, message.id)}
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
          <div className="chat-input-shell">
            <button
              className="image-ocr-button"
              type="button"
              onClick={() => fileInputRef.current?.click()}
              title={copy.imageOcr}
            >
              <ImageIcon />
            </button>
            <input
              ref={fileInputRef}
              className="image-ocr-input"
              type="file"
              accept="image/*"
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (!file) return
                setSelectedImageFile(file)
                readFileAsDataUrl(file)
                  .then((dataUrl) => {
                    setSelectedImagePreview(dataUrl)
                    setOcrState({ name: file.name, status: 'attached' })
                  })
                  .catch((error) => {
                    console.error('Preview failed', error)
                    setSelectedImageFile(null)
                    setSelectedImagePreview('')
                    setOcrState({ name: file.name, status: 'error' })
                  })
                  .finally(() => {
                    event.target.value = ''
                  })
              }}
            />
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
          {ocrState ? (
            <div className={`ocr-float ${ocrState.status}`} title={ocrState.name}>
              <span className="ocr-float-count">1</span>
              <span className="ocr-float-label">
                {ocrState.status === 'attached'
                  ? copy.imageAttached
                  : ocrState.status === 'loading'
                    ? copy.ocrReading
                    : ocrState.status === 'ready'
                      ? copy.ocrReady
                      : copy.ocrFailed}
              </span>
              <button
                type="button"
                className="ocr-float-clear"
                onClick={() => {
                  setOcrState(null)
                  setSelectedImageFile(null)
                  setSelectedImagePreview('')
                }}
              >
                x
              </button>
            </div>
          ) : null}
        </div>
        <button
          className="send-button"
          type="button"
          disabled={isStreaming && !inputValue.trim() && !selectedImageFile}
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
    </div>
  )
}

