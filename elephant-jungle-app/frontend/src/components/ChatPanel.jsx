import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSpriteOrbit } from '../hooks/useSpriteOrbit'
import { useSpriteHoverNews } from '../hooks/useSpriteHoverNews'
import { useTheme } from '../hooks/useTheme'
import ThemeToggle from './ThemeToggle'

const REQUEST_TIMEOUT_MS = 90000
const SPRITE_BRIEF_REFRESH_MS = 15 * 60 * 1000
const SPRITE_BUBBLE_TYPE_MS = 18
const SPRITE_BUBBLE_HOLD_MS = 1500
const MOBILE_KEYBOARD_CLOSE_DELTA = 96
const GUEST_MESSAGES_STORAGE_KEY = 'elephant_guest_messages_v1'

function shortEmail(email) {
  const atIndex = email.indexOf('@')
  if (atIndex <= 0) return email
  const prefix = email.slice(0, Math.min(atIndex, 3))
  return `${prefix}...`
}

function loadStoredGuestMessages() {
  if (typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(GUEST_MESSAGES_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((item) => item && typeof item === 'object')
  } catch {
    return []
  }
}

function hasGuestConversation(messages) {
  return (messages || []).some((message) => message?.role === 'user' && String(message?.text || '').trim())
}

function cleanHeadlineTitle(title = '') {
  return String(title)
    .replace(/\s+/g, ' ')
    .replace(/\s+[|·-]\s+[^|·-]+$/, '')
    .trim()
}

function toBubbleSnippet(title, language) {
  const cleaned = cleanHeadlineTitle(title)
  if (!cleaned) return ''

  if (language === 'zh') {
    return cleaned.replace(/\s+/g, '').slice(0, 12)
  }

  const normalized = cleaned.replace(/[^A-Za-z0-9$%+\-\u4e00-\u9fff ]+/g, ' ').replace(/\s+/g, ' ').trim()
  if (!normalized) return cleaned.slice(0, 14)
  return normalized.slice(0, 16).trim()
}

function extractBriefSnippets(payload, language) {
  const items = [...(payload?.social || []), ...(payload?.news || [])]
  const seen = new Set()
  const snippets = []

  for (const item of items) {
    const snippet = toBubbleSnippet(item?.title || '', language)
    if (!snippet || seen.has(snippet)) continue
    seen.add(snippet)
    snippets.push(snippet)
    if (snippets.length >= 8) break
  }

  return snippets
}

const COPY = {
  en: {
    welcome: "Hello, I'm your Elephant Jungle assistant. What can I help you with?",
    login: 'Login',
    loginTitle: 'Email Login',
    emailPlaceholder: 'Email address',
    codePlaceholder: 'Verification code',
    sendCode: 'Send Code',
    differentEmail: 'Use a different email',
    confirmLogin: 'Confirm',
    cancel: 'Cancel',
    logout: 'Logout',
    guest: 'Guest',
    copy: 'Copy',
    copied: 'Copied',
    retry: 'Retry',
    thinkingLabel: 'Thinking...',
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
    loginPrompt: 'Please login to continue the conversation. Tap the avatar in the top-right corner to sign in.',
    workCreated: 'Task created and saved in Work.',
    workConfirmHint: 'Reply "confirm" to save this task in Work.',
    workLoginRequired: 'Please login first. Work tasks are tied to your account and email.',
  },
  zh: {
    welcome: "Hello, I'm your Elephant Jungle assistant. 你好，请问需要什么帮助？",
    login: 'Login',
    loginTitle: '邮箱登录',
    emailPlaceholder: '邮箱地址',
    codePlaceholder: '验证码',
    sendCode: '发送验证码',
    differentEmail: '换个邮箱',
    confirmLogin: '确认',
    cancel: '取消',
    logout: '退出登录',
    guest: 'Guest',
    copy: '复制',
    copied: '已复制',
    retry: '重试',
    thinkingLabel: '想一下...',
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
    loginPrompt: '请登录后继续对话。点击右上角头像进行登录。',
    workCreated: '任务已创建，并已保存到 Work。',
    workConfirmHint: '回复“确认”就会保存到 Work。',
    workLoginRequired: '请先登录。Work 任务会绑定到你的账号和邮箱。',
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

function isWorkConfirmIntent(text) {
  const normalized = String(text || '').trim().toLowerCase()
  return ['confirm', 'yes', 'ok', 'create it', 'save it', '确认', '确定', '创建', '保存'].includes(normalized)
}

function isWorkTaskIntent(text) {
  const normalized = String(text || '').toLowerCase()
  const hasWorkVerb = /(email|mail|alert|notify|remind|提醒|通知|邮件|发邮件|记录|创建任务|任务)/i.test(text)
  const hasTrigger = /(when|if|below|above|under|over|drop|drops|rise|rises|当|如果|跌破|低于|涨破|高于|超过)/i.test(text)
  const hasPrice = /(\d+(?:\.\d+)?\s*(usd|usdt|美元|u)?|\$)/i.test(text)
  const mentionsWork = normalized.includes('work')
  return (hasWorkVerb && hasTrigger && hasPrice) || (mentionsWork && hasTrigger)
}

async function readJsonResponse(response, fallbackMessage) {
  const contentType = response.headers.get('content-type') || ''
  if (!contentType.includes('application/json')) {
    throw new Error(fallbackMessage)
  }
  return response.json()
}

export default function ChatPanel({ apiBase, language, setLanguage, mobileOnly = false }) {
  const copy = COPY[language] || COPY.en
  const { theme, setTheme } = useTheme()
  const [messages, setMessages] = useState(() => loadStoredGuestMessages())
  const [authToken, setAuthToken] = useState(() => {
    if (typeof window === 'undefined') return ''
    return window.localStorage.getItem('elephant_auth_token') || ''
  })
  const [userEmail, setUserEmail] = useState(() => {
    if (typeof window === 'undefined') return ''
    return window.localStorage.getItem('elephant_user_email') || ''
  })
  const [accountSheetOpen, setAccountSheetOpen] = useState(false)
  const [emailDraft, setEmailDraft] = useState('')
  const [codeDraft, setCodeDraft] = useState('')
  const [codeSent, setCodeSent] = useState(false)
  const [authLoading, setAuthLoading] = useState(false)
  const [authError, setAuthError] = useState('')
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const [historyOffset, setHistoryOffset] = useState(0)
  const [hasMoreHistory, setHasMoreHistory] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [guestChatUsed, setGuestChatUsed] = useState(() => hasGuestConversation(loadStoredGuestMessages()))
  const [inputValue, setInputValue] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [ocrState, setOcrState] = useState(null)
  const [selectedImageFile, setSelectedImageFile] = useState(null)
  const [selectedImagePreview, setSelectedImagePreview] = useState('')
  const [spriteBubbleText, setSpriteBubbleText] = useState('')
  const [spriteBriefSnippets, setSpriteBriefSnippets] = useState(() =>
    language === 'zh'
      ? ['BTC新高', 'ETF流向', 'ETH动态', 'Meme热度']
      : ['BTC move', 'ETF flow', 'ETH watch', 'Meme heat'],
  )
  const chatBoxRef = useRef(null)
  const historySentinelRef = useRef(null)
  const chatSpriteTrackRef = useRef(null)
  const chatSpriteShellRef = useRef(null)
  const inputSpriteTrackRef = useRef(null)
  const inputSpriteShellRef = useRef(null)
  const welcomeStartedRef = useRef(messages.length > 0)
  const activeRequestRef = useRef(null)
  const activeRunIdRef = useRef(0)
  const activeBotIdRef = useRef(null)
  const fileInputRef = useRef(null)
  const workSessionRef = useRef('')
  const workDraftRef = useRef(null)
  const textInputRef = useRef(null)
  const topbarRef = useRef(null)

  const { spriteMode, boost, cruise, pauseSprite, resumeSprite } = useSpriteOrbit(
    mobileOnly
      ? [{ trackRef: chatSpriteTrackRef, shellRef: chatSpriteShellRef, direction: 1 }]
      : [
          { trackRef: chatSpriteTrackRef, shellRef: chatSpriteShellRef, direction: 1 },
          { trackRef: inputSpriteTrackRef, shellRef: inputSpriteShellRef, direction: -1 },
        ],
  )

  const hoverNewsChat = useSpriteHoverNews(apiBase, 2)
  const hoverNewsInput = useSpriteHoverNews(apiBase, 3)

  const chatBubbleText = hoverNewsChat.isHovered ? hoverNewsChat.bubbleText : spriteBubbleText
  const inputBubbleText = hoverNewsInput.isHovered ? hoverNewsInput.bubbleText : spriteBubbleText

  const scrollToBottom = () => {
    window.requestAnimationFrame(() => {
      if (chatBoxRef.current) {
        chatBoxRef.current.scrollTop = chatBoxRef.current.scrollHeight
      }
    })
  }

  const snapViewportToTop = () => {
    if (!mobileOnly || typeof window === 'undefined') return

    const jumpTop = () => {
      window.scrollTo(0, 0)
      document.documentElement.scrollTop = 0
      document.body.scrollTop = 0
      topbarRef.current?.scrollIntoView?.({ block: 'start', inline: 'nearest' })
    }

    window.requestAnimationFrame(() => {
      jumpTop()
      window.requestAnimationFrame(jumpTop)
    })
  }

  const askBackend = async (query, controller, options = {}, onStatus = null) => {
    const { useRag = true } = options
    let didTimeout = false
    const timeoutId = window.setTimeout(() => {
      didTimeout = true
      controller.abort()
    }, REQUEST_TIMEOUT_MS)

    try {
      const headers = { 'Content-Type': 'application/json' }
      const token = window.localStorage.getItem('elephant_auth_token')
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }

      const workHeaders = { 'Content-Type': 'application/json' }
      if (token && token !== 'cookie') {
        workHeaders.Authorization = `Bearer ${token}`
      }

      if (isWorkConfirmIntent(query) && workSessionRef.current && workDraftRef.current) {
        const response = await fetch(`${apiBase}/work/tasks/confirm`, {
          method: 'POST',
          headers: workHeaders,
          credentials: 'include',
          body: JSON.stringify({ session_id: workSessionRef.current }),
          signal: controller.signal,
        })
        const payload = await readJsonResponse(response, copy.requestFailed)
        if (!response.ok) {
          if (response.status === 401) throw new Error(copy.workLoginRequired)
          throw new Error(payload.detail || copy.requestFailed)
        }
        workSessionRef.current = ''
        workDraftRef.current = null
        window.dispatchEvent(new CustomEvent('work-tasks-updated', { detail: payload.task }))
        return copy.workCreated
      }

      if (isWorkTaskIntent(query)) {
        const response = await fetch(`${apiBase}/work/assistant/message`, {
          method: 'POST',
          headers: workHeaders,
          credentials: 'include',
          body: JSON.stringify({
            session_id: workSessionRef.current || undefined,
            message: query,
            language,
          }),
          signal: controller.signal,
        })
        const payload = await readJsonResponse(response, copy.requestFailed)
        if (!response.ok) {
          if (response.status === 401) throw new Error(copy.workLoginRequired)
          throw new Error(payload.detail || copy.requestFailed)
        }
        workSessionRef.current = payload.session_id || ''
        workDraftRef.current = payload.draft_task || null
        const assistantMessage = payload.assistant_message || copy.noAnswer
        return payload.needs_confirmation ? `${assistantMessage}\n\n${copy.workConfirmHint}` : assistantMessage
      }

      const response = await fetch(`${apiBase}/chat/stream`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ query, top_k: 5, auto_intent: true }),
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

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let answerText = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop() || ''

        for (const part of parts) {
          const lines = part.split('\n')
          let eventType = ''
          let eventData = ''

          for (const line of lines) {
            if (line.startsWith('event: ')) {
              eventType = line.slice(7).trim()
            } else if (line.startsWith('data: ')) {
              eventData = line.slice(6).trim()
            }
          }

          if (!eventData) continue

          try {
            const parsed = JSON.parse(eventData)
            if (eventType === 'intent' || eventType === 'status' || eventType === 'tool_call' || eventType === 'tool_result') {
              if (onStatus) onStatus(parsed.message || parsed.text || '')
            } else if (eventType === 'answer') {
              answerText = parsed.text || ''
            } else if (eventType === 'error') {
              throw new Error(parsed.message || copy.requestFailed)
            }
          } catch (e) {
            if (e.message !== 'Unexpected token') throw e
          }
        }
      }

      return answerText || copy.noAnswer
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

  const frames = useMemo(() => copy.thinkingFrames, [copy.thinkingFrames])
  const frameDelays = useMemo(() => [55, 65, 75, 85, 95, 110, 125, 145, 175, 210, 250], [])

  const stopThinkingRef = useRef(null)

  const streamThinkingText = (messageId) => {
    if (stopThinkingRef.current) {
      window.clearTimeout(stopThinkingRef.current)
      stopThinkingRef.current = null
    }
    let frameIndex = 0
    setMessages((prev) =>
      prev.map((m) =>
        m.id === messageId
          ? { ...m, text: frames[0], thinking: true }
          : m,
      ),
    )
    scrollToBottom()

    const LOOP_START = 1

    const tick = () => {
      frameIndex += 1
      if (frameIndex >= frames.length) {
        frameIndex = LOOP_START
      }
      setMessages((prev) =>
        prev.map((m) =>
          m.id === messageId
            ? { ...m, text: frames[frameIndex], thinking: true }
            : m,
        ),
      )
      scrollToBottom()
      stopThinkingRef.current = window.setTimeout(tick, frameDelays[frameIndex] || 120)
    }

    stopThinkingRef.current = window.setTimeout(tick, frameDelays[0] || 55)
  }

  const streamAssistantText = (messageId, fullText, query, options = {}) => {
    const { hideActions = false } = options
    if (stopThinkingRef.current) {
      window.clearTimeout(stopThinkingRef.current)
      stopThinkingRef.current = null
    }
    const chars = [...fullText]
    let revealed = 0
    setMessages((prev) =>
      prev.map((m) =>
        m.id === messageId
          ? { ...m, text: '', thinking: false, hideActions: true, hiddenWhilePending: false, query }
          : m,
      ),
    )
    scrollToBottom()

    const intervalId = window.setInterval(() => {
      revealed += 1
      if (revealed >= chars.length) {
        window.clearInterval(intervalId)
        setMessages((prev) =>
          prev.map((m) =>
            m.id === messageId
              ? { ...m, text: fullText, thinking: false, hideActions, hiddenWhilePending: false }
              : m,
          ),
        )
        scrollToBottom()
        return
      }
      setMessages((prev) =>
        prev.map((m) =>
          m.id === messageId
            ? { ...m, text: chars.slice(0, revealed).join(''), thinking: false, hideActions: true }
            : m,
        ),
      )
      scrollToBottom()
    }, 20)
  }

  useEffect(() => {
    let cancelled = false

    const loadBriefSnippets = async () => {
      try {
        const response = await fetch(`${apiBase}/market/briefs`)
        if (!response.ok) return
        const payload = await response.json()
        const snippets = extractBriefSnippets(payload, language)
        if (!cancelled && snippets.length) {
          setSpriteBriefSnippets(snippets)
        }
      } catch (error) {
        console.error('Sprite briefs fallback', error)
      }
    }

    loadBriefSnippets()
    const timer = window.setInterval(loadBriefSnippets, SPRITE_BRIEF_REFRESH_MS)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [apiBase, language])

  useEffect(() => {
    if (!spriteBriefSnippets.length) {
      setSpriteBubbleText('')
      return undefined
    }

    let snippetIndex = 0
    let charIndex = 0
    let typeTimer = null
    let holdTimer = null
    let stopped = false

    const typeNext = () => {
      if (stopped) return
      const snippet = spriteBriefSnippets[snippetIndex % spriteBriefSnippets.length] || ''
      if (!snippet) return
      charIndex += 1
      setSpriteBubbleText(snippet.slice(0, charIndex))
      if (charIndex < snippet.length) {
        typeTimer = window.setTimeout(typeNext, SPRITE_BUBBLE_TYPE_MS)
        return
      }
      holdTimer = window.setTimeout(() => {
        snippetIndex = (snippetIndex + 1) % spriteBriefSnippets.length
        charIndex = 0
        setSpriteBubbleText('')
        typeTimer = window.setTimeout(typeNext, 120)
      }, SPRITE_BUBBLE_HOLD_MS)
    }

    setSpriteBubbleText('')
    typeTimer = window.setTimeout(typeNext, 120)

    return () => {
      stopped = true
      if (typeTimer) window.clearTimeout(typeTimer)
      if (holdTimer) window.clearTimeout(holdTimer)
    }
  }, [spriteBriefSnippets])

  useEffect(() => {
    if (!mobileOnly || typeof window === 'undefined') return undefined

    const root = document.documentElement
    const body = document.body
    const previousHtmlOverflow = root.style.overflow
    const previousBodyOverflow = body.style.overflow
    const previousHtmlOverscroll = root.style.overscrollBehaviorY
    const previousBodyOverscroll = body.style.overscrollBehaviorY

    root.style.overflow = 'hidden'
    body.style.overflow = 'hidden'
    root.style.overscrollBehaviorY = 'none'
    body.style.overscrollBehaviorY = 'none'

    let maxViewportHeight = window.visualViewport?.height || window.innerHeight

    const handleViewportResize = () => {
      const currentHeight = window.visualViewport?.height || window.innerHeight
      if (currentHeight > maxViewportHeight) {
        maxViewportHeight = currentHeight
      }
      if (currentHeight >= maxViewportHeight - MOBILE_KEYBOARD_CLOSE_DELTA) {
        snapViewportToTop()
      }
    }

    const viewport = window.visualViewport
    viewport?.addEventListener('resize', handleViewportResize)
    window.addEventListener('orientationchange', snapViewportToTop)

    return () => {
      viewport?.removeEventListener('resize', handleViewportResize)
      window.removeEventListener('orientationchange', snapViewportToTop)
      root.style.overflow = previousHtmlOverflow
      body.style.overflow = previousBodyOverflow
      root.style.overscrollBehaviorY = previousHtmlOverscroll
      body.style.overscrollBehaviorY = previousBodyOverscroll
    }
  }, [mobileOnly])

  useEffect(() => {
    setEmailDraft(userEmail || '')
  }, [userEmail, accountSheetOpen])

  const authFetch = async (path, body) => {
    const response = await fetch(`${apiBase}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}))
      throw new Error(payload.detail || 'Request failed')
    }
    return response.json()
  }

  const checkAuth = useCallback(async () => {
    const token = window.localStorage.getItem('elephant_auth_token')
    const email = window.localStorage.getItem('elephant_user_email')
    if (token && email) {
      try {
        const response = await fetch(`${apiBase}/auth/me`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (!response.ok) throw new Error('invalid token')
        setAuthToken(token)
        setUserEmail(email)
        return
      } catch {
        window.localStorage.removeItem('elephant_auth_token')
        window.localStorage.removeItem('elephant_user_email')
      }
    }
    // Check if httpOnly cookie still has a valid session
    try {
      const response = await fetch(`${apiBase}/auth/me`)
      if (response.ok) {
        const data = await response.json()
        const email = data.user?.email || ''
        setAuthToken('cookie')
        setUserEmail(email)
        if (email) {
          window.localStorage.setItem('elephant_user_email', email)
        }
      }
    } catch {
      // No cookie session
    }
  }, [apiBase])

  useEffect(() => {
    checkAuth()
  }, [checkAuth])

  useEffect(() => {
    if (typeof window === 'undefined') return
    const persistableMessages = messages.filter((message) => {
      if (!message || typeof message !== 'object') return false
      if (message.thinking || message.hiddenWhilePending) return false
      return Boolean(String(message.text || '').trim() || String(message.imageUrl || '').trim())
    })
    if (!persistableMessages.length) {
      window.localStorage.removeItem(GUEST_MESSAGES_STORAGE_KEY)
      return
    }
    window.localStorage.setItem(GUEST_MESSAGES_STORAGE_KEY, JSON.stringify(persistableMessages))
  }, [messages])

  const loadChatHistory = useCallback(async () => {
    const token = window.localStorage.getItem('elephant_auth_token')
    const headers = token ? { Authorization: `Bearer ${token}` } : {}
    try {
      const response = await fetch(`${apiBase}/chat/history?limit=10&offset=0`, { headers })
      if (!response.ok) return
      const data = await response.json()
      const history = []
      for (const msg of (data.messages || [])) {
        history.push({
          id: `hist-user-${msg.id}`,
          role: 'user',
          text: msg.user_content,
          query: '',
          hideActions: true,
          hiddenWhilePending: false,
        })
        history.push({
          id: `hist-bot-${msg.id}`,
          role: 'bot',
          text: msg.bot_content,
          query: msg.user_content || '',
          hideActions: true,
          hiddenWhilePending: false,
        })
      }
      if (history.length) {
        setMessages(history)
        setHistoryLoaded(true)
        setHistoryOffset(data.messages.length)
        setHasMoreHistory(data.total > data.messages.length)
      }
    } catch {
      // silently fail
    }
  }, [apiBase])

  const loadMoreMessages = useCallback(async () => {
    if (loadingMore || !hasMoreHistory) return
    setLoadingMore(true)
    const token = window.localStorage.getItem('elephant_auth_token')
    const headers = token ? { Authorization: `Bearer ${token}` } : {}
    try {
      const response = await fetch(`${apiBase}/chat/history?limit=10&offset=${historyOffset}`, { headers })
      if (!response.ok) return
      const data = await response.json()
      const older = []
      for (const msg of (data.messages || [])) {
        older.push({
          id: `hist-user-${msg.id}`,
          role: 'user',
          text: msg.user_content,
          query: '',
          hideActions: true,
          hiddenWhilePending: false,
        })
        older.push({
          id: `hist-bot-${msg.id}`,
          role: 'bot',
          text: msg.bot_content,
          query: msg.user_content || '',
          hideActions: true,
          hiddenWhilePending: false,
        })
      }
      if (older.length) {
        const prevScrollHeight = chatBoxRef.current?.scrollHeight || 0
        setMessages(prev => [...older, ...prev])
        setHistoryOffset(prev => prev + data.messages.length)
        setHasMoreHistory(data.total > historyOffset + data.messages.length)
        requestAnimationFrame(() => {
          if (chatBoxRef.current) {
            chatBoxRef.current.scrollTop = chatBoxRef.current.scrollHeight - prevScrollHeight
          }
        })
      } else {
        setHasMoreHistory(false)
      }
    } catch {
      // silently fail
    } finally {
      setLoadingMore(false)
    }
  }, [apiBase, historyOffset, hasMoreHistory, loadingMore])

  // IntersectionObserver for scroll-to-top lazy load
  useEffect(() => {
    const sentinel = historySentinelRef.current
    const chatBox = chatBoxRef.current
    if (!sentinel || !chatBox || !hasMoreHistory) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && hasMoreHistory && !loadingMore) {
          loadMoreMessages()
        }
      },
      { root: chatBox, threshold: 0.1 },
    )
    observer.observe(sentinel)
    return () => observer.disconnect()
  }, [hasMoreHistory, loadingMore, loadMoreMessages])

  useEffect(() => {
    if (authToken && !historyLoaded) {
      loadChatHistory()
    }
  }, [authToken, historyLoaded, loadChatHistory])

  const sendVerificationCode = async () => {
    const normalized = emailDraft.trim()
    if (!normalized || !normalized.includes('@')) {
      setAuthError('Please enter a valid email address')
      return
    }
    setAuthLoading(true)
    setAuthError('')
    try {
      await authFetch('/auth/send-code', { email: normalized })
      setCodeSent(true)
    } catch (error) {
      setAuthError(error.message)
    } finally {
      setAuthLoading(false)
    }
  }

  const verifyAndLogin = async () => {
    const code = codeDraft.trim()
    if (!code || code.length !== 6) {
      setAuthError('Please enter the 6-digit verification code')
      return
    }
    setAuthLoading(true)
    setAuthError('')
    try {
      const data = await authFetch('/auth/verify-code', {
        email: emailDraft.trim(),
        code,
      })
      setAuthToken(data.token)
      setUserEmail(data.user.email)
      if (typeof window !== 'undefined') {
        window.localStorage.setItem('elephant_auth_token', data.token)
        window.localStorage.setItem('elephant_user_email', data.user.email)
      }
      setHistoryLoaded(false)
      setAccountSheetOpen(false)
      resetAuthForm()
    } catch (error) {
      setAuthError(error.message)
    } finally {
      setAuthLoading(false)
    }
  }

  const logout = () => {
    fetch(`${apiBase}/auth/logout`, { method: 'POST' }).catch(() => {})
    setAuthToken('')
    setUserEmail('')
    setMessages([])
    setHistoryLoaded(false)
    setGuestChatUsed(false)
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem('elephant_auth_token')
      window.localStorage.removeItem('elephant_user_email')
      window.localStorage.removeItem(GUEST_MESSAGES_STORAGE_KEY)
    }
    setAccountSheetOpen(false)
    resetAuthForm()
    // Re-trigger welcome message
    welcomeStartedRef.current = false
  }

  const resetAuthForm = () => {
    setEmailDraft('')
    setCodeDraft('')
    setCodeSent(false)
    setAuthError('')
  }

  const openAccountSheet = () => {
    resetAuthForm()
    setEmailDraft(userEmail || '')
    setAccountSheetOpen(true)
  }

  useEffect(() => {
    if (!accountSheetOpen) {
      resetAuthForm()
    }
  }, [accountSheetOpen])

  useEffect(() => {
    const welcomeId = 'bot-welcome'

    if (!welcomeStartedRef.current) {
      welcomeStartedRef.current = true
      setMessages([{ id: welcomeId, role: 'bot', text: '', query: '', hideActions: true }])
      scrollToBottom()
      streamAssistantText(welcomeId, copy.welcome, '', { hideActions: true })
      return
    }

    setMessages((prev) => {
      if (prev.length === 1 && prev[0]?.id === welcomeId) {
        return [{ ...prev[0], text: copy.welcome, query: '' }]
      }
      return prev
    })
  }, [copy.welcome])

  const interruptActiveReply = () => {
    activeRunIdRef.current += 1
    if (stopThinkingRef.current) {
      window.clearTimeout(stopThinkingRef.current)
      stopThinkingRef.current = null
    }
    if (activeRequestRef.current) {
      activeRequestRef.current.abort()
      activeRequestRef.current = null
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

    // Guest gate: only 1 free message before login
    if (!authToken && guestChatUsed) {
      setIsStreaming(false)
      setSelectedImageFile(null)
      setSelectedImagePreview('')
      setOcrState(null)
      const botId = `bot-blocked-${Date.now()}`
      setMessages((prev) => [...prev, { id: botId, role: 'bot', text: '', thinking: true, query: '' }])
      scrollToBottom()
      streamThinkingText(botId)
      setTimeout(() => {
        streamAssistantText(botId, copy.loginPrompt, '')
      }, 400)
      return
    }

    if (!authToken) setGuestChatUsed(true)

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
          message.id === retryMessageId ? { ...message, text: '', thinking: true } : message,
        )
      }
      next.push({ id: botId, role: 'bot', text: '', thinking: true, query: userText })
      return next
    })
    scrollToBottom()
    if (retryMessageId) {
      streamThinkingText(retryMessageId)
    } else {
      streamThinkingText(botId)
    }

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

      const answer = await askBackend(backendQuery, controller, { useRag }, (statusText) => {
	        setMessages((prev) =>
	          prev.map((m) =>
	            m.id === botId ? { ...m, statusText } : m,
	          ),
	        )
	      })
      if (runId !== activeRunIdRef.current) return
      streamAssistantText(botId, answer, backendQuery)
      snapViewportToTop()
      setSelectedImageFile(null)
      setSelectedImagePreview('')
      setOcrState(null)
    } catch (error) {
      if (error.name === 'AbortError') {
        return
      }
      if (runId !== activeRunIdRef.current) return
      if (selectedImageFile) {
        setSelectedImageFile(null)
        setSelectedImagePreview('')
        setOcrState(null)
      }
      streamAssistantText(botId, `${copy.backendError}: ${error.message}`, query)
      snapViewportToTop()
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
    <div
      className={`right-col ${mobileOnly ? 'mobile-chat-col' : ''}`}
    >
      <div ref={topbarRef} className={`right-topbar ${mobileOnly ? 'mobile-chat-topbar' : ''}`}>
        <div className={`right-topbar-left ${mobileOnly ? 'mobile-chat-topbar-left' : ''}`}>
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
          <ThemeToggle theme={theme} setTheme={setTheme} language={language} />
        </div>
        <div className={`right-topbar-right ${mobileOnly ? 'mobile-chat-topbar-right' : ''}`}>
          <button
            className="account-chip"
            type="button"
            onClick={openAccountSheet}
          >
            <span className="account-chip-avatar" aria-hidden="true">
              {userEmail ? userEmail.slice(0, 1).toUpperCase() : 'E'}
            </span>
            <div className="account-chip-copy">
              {userEmail ? (
                <span className="account-chip-email">{shortEmail(userEmail)}</span>
              ) : (
                <div className="account-chip-actions">
                  <span className="account-chip-action">{copy.login}</span>
                </div>
              )}
            </div>
          </button>
        </div>
      </div>
      <div className={`right-panel ${mobileOnly ? 'mobile-chat-panel' : ''}`}>
      <div className={`chat-stage ${mobileOnly ? 'mobile-chat-stage' : ''}`}>
        <div className="chat-sprite-track" ref={chatSpriteTrackRef} aria-hidden="true">
          <div className="sprite-shell facing-right" ref={chatSpriteShellRef}
            onMouseEnter={(e) => { hoverNewsChat.handleMouseEnter(e); pauseSprite(0) }}
            onMouseLeave={(e) => { hoverNewsChat.handleMouseLeave(e); resumeSprite(0) }}
          >
            {chatBubbleText ? <div className="sprite-bubble">{chatBubbleText}</div> : null}
            <div className={`sprite-avatar ${spriteMode}`} />
          </div>
        </div>
        <div className="chat-box" ref={chatBoxRef}>
          {hasMoreHistory ? (
            <div ref={historySentinelRef} className="history-sentinel">
              {loadingMore ? (language === 'zh' ? '加载中...' : 'Loading...') : (language === 'zh' ? '↑ 加载更多' : '↑ Load more')}
            </div>
          ) : null}
          {messages
            .filter((message) => !(message.hiddenWhilePending && !message.text.trim()))
            .map((message) => (
              <div className={`msg ${message.role} ${message.role === 'bot' ? 'assistant' : ''}`} key={message.id}>
                <div className={`msg-content ${message.thinking ? 'thinking-inline' : ''} ${message.imageUrl ? 'has-image' : ''}`}>
                  {message.imageUrl ? (
                    <img className="chat-image-preview" src={message.imageUrl} alt="uploaded content" />
                  ) : null}
                  {message.text ? <div>{message.text}</div> : null}
                  {message.thinking && message.statusText ? (
                    <div className="thinking-status">{message.statusText}</div>
                  ) : null}
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
      <div className={`input-row ${mobileOnly ? 'mobile-chat-input-row' : ''}`}>
        <div className="input-wrap">
          {!mobileOnly ? (
            <div className="input-sprite-track" ref={inputSpriteTrackRef} aria-hidden="true">
              <div className="sprite-shell facing-left" ref={inputSpriteShellRef}
                onMouseEnter={(e) => { hoverNewsInput.handleMouseEnter(e); pauseSprite(1) }}
                onMouseLeave={(e) => { hoverNewsInput.handleMouseLeave(e); resumeSprite(1) }}
              >
                {inputBubbleText ? <div className="sprite-bubble">{inputBubbleText}</div> : null}
                <div className={`sprite-avatar ${spriteMode}`} />
              </div>
            </div>
          ) : null}
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
              ref={textInputRef}
              type="text"
              value={inputValue}
              placeholder={copy.placeholder}
              onChange={(event) => {
                setInputValue(event.target.value)
                boost()
              }}
              onCompositionStart={() => {
                if (textInputRef.current) textInputRef.current.dataset.composing = 'true'
              }}
              onCompositionEnd={() => {
                if (textInputRef.current) textInputRef.current.dataset.composing = 'false'
              }}
              onBlur={() => {
                cruise()
                window.setTimeout(snapViewportToTop, 90)
              }}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && event.currentTarget.dataset.composing !== 'true') {
                  const query = inputValue
                  setInputValue('')
                  if (mobileOnly) {
                    textInputRef.current?.blur()
                  }
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
            if (mobileOnly) {
              textInputRef.current?.blur()
            }
            sendQuery(query)
          }}
        >
          {copy.send}
        </button>
      </div>
      </div>
      {accountSheetOpen ? (
        <div className="account-sheet-backdrop" onClick={() => {
            if (document.activeElement?.tagName === 'INPUT') return;
            setAccountSheetOpen(false);
          }}>
          <div className="account-sheet" onClick={(event) => event.stopPropagation()}>
            <div className="account-sheet-title">{copy.loginTitle}</div>
            {userEmail ? (
              <>
                <div className="account-sheet-current">{userEmail}</div>
                <div className="account-sheet-actions-row">
                  <button type="button" className="account-sheet-btn secondary" onClick={() => setAccountSheetOpen(false)}>
                    {copy.cancel}
                  </button>
                  <button type="button" className="account-sheet-btn primary" onClick={logout}>
                    {copy.logout}
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="account-sheet-inputs">
                  <input
                    className="account-sheet-input"
                    type="email"
                    value={emailDraft}
                    placeholder={copy.emailPlaceholder}
                    disabled={codeSent}
                    onChange={(event) => setEmailDraft(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' && !event.isComposing && !codeSent) {
                        sendVerificationCode()
                      }
                    }}
                  />
                  {codeSent ? (
                    <input
                      className="account-sheet-input account-sheet-code-input"
                      type="text"
                      inputMode="numeric"
                      maxLength={6}
                      value={codeDraft}
                      placeholder={copy.codePlaceholder}
                      autoFocus
                      onChange={(event) => setCodeDraft(event.target.value.replace(/\D/g, ''))}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') {
                          verifyAndLogin()
                        }
                      }}
                    />
                  ) : null}
                </div>
                {authError ? (
                  <div className="account-sheet-error">{authError}</div>
                ) : null}
                <div className="account-sheet-actions-row">
                  <button type="button" className="account-sheet-btn secondary" onClick={() => setAccountSheetOpen(false)}>
                    {copy.cancel}
                  </button>
                  {codeSent ? (
                    <button
                      type="button"
                      className="account-sheet-btn primary"
                      disabled={authLoading || codeDraft.length !== 6}
                      onClick={verifyAndLogin}
                    >
                      {authLoading ? '...' : copy.confirmLogin}
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="account-sheet-btn primary"
                      disabled={authLoading || !emailDraft.trim()}
                      onClick={sendVerificationCode}
                    >
                      {authLoading ? '...' : copy.sendCode}
                    </button>
                  )}
                </div>
                {codeSent ? (
                  <button
                    type="button"
                    className="account-sheet-back-link"
                    onClick={() => { setCodeSent(false); setCodeDraft(''); setAuthError('') }}
                  >
                    {copy.differentEmail}
                  </button>
                ) : null}
              </>
            )}
          </div>
        </div>
      ) : null}
    </div>
  )
}
