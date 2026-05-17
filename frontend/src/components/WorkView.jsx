import { useEffect, useMemo, useState } from 'react'

const COPY = {
  en: {
    kicker: 'Work',
    title: 'Task workflows',
    subtitle: 'Create a workflow task in plain language. The first version supports price-triggered email alerts.',
    inputPlaceholder: 'Example: Email me when SUI drops below 1 USD.',
    send: 'Plan task',
    confirm: 'Confirm task',
    activeTasks: 'Active tasks',
    loginRequired: 'Please login first. Work tasks are tied to your account and email.',
    noTasks: 'No active tasks yet.',
    cancel: 'Cancel',
    drafting: 'Drafting task...',
    loading: 'Loading tasks...',
    missingDraft: 'No draft task to confirm.',
    confirmed: 'Task created and monitoring has started.',
    assistant: 'Assistant',
    errorPrefix: 'Error',
  },
  zh: {
    kicker: 'Work',
    title: '任务工作流',
    subtitle: '你可以直接用自然语言布置任务。第一版先支持价格触发发邮件。',
    inputPlaceholder: '例如：当 SUI 跌破 1 美元就给我发邮件。',
    send: '规划任务',
    confirm: '确认创建',
    activeTasks: '活动任务',
    loginRequired: '请先登录。Work 任务会绑定到你的账号和邮箱。',
    noTasks: '暂时还没有活动任务。',
    cancel: '取消',
    drafting: '正在规划任务...',
    loading: '正在加载任务...',
    missingDraft: '没有可确认的任务草稿。',
    confirmed: '任务已创建，监控已经启动。',
    assistant: '助手',
    errorPrefix: '错误',
  },
}


function operatorLabel(operator, language) {
  if ((language || 'en').startsWith('zh')) {
    return operator === 'below' ? '跌破' : '涨破'
  }
  return operator === 'below' ? 'below' : 'above'
}


async function readJson(response) {
  const contentType = response.headers.get('content-type') || ''
  if (!contentType.includes('application/json')) {
    throw new Error('Work API returned a web page instead of JSON. Please refresh and check the API address.')
  }
  return response.json()
}


export default function WorkView({ apiBase, language }) {
  const copy = COPY[language] || COPY.en
  const [sessionId, setSessionId] = useState('')
  const [inputValue, setInputValue] = useState('')
  const [assistantMessage, setAssistantMessage] = useState('')
  const [draftTask, setDraftTask] = useState(null)
  const [needsConfirmation, setNeedsConfirmation] = useState(false)
  const [tasks, setTasks] = useState([])
  const [loadingTasks, setLoadingTasks] = useState(true)
  const [working, setWorking] = useState(false)
  const [feedback, setFeedback] = useState('')
  const [authToken, setAuthToken] = useState(() => (
    typeof window === 'undefined' ? '' : (window.localStorage.getItem('elephant_auth_token') || '')
  ))
  const [userEmail, setUserEmail] = useState(() => (
    typeof window === 'undefined' ? '' : (window.localStorage.getItem('elephant_user_email') || '')
  ))

  const loggedIn = Boolean(userEmail || authToken)

  const authHeaders = useMemo(() => {
    const headers = { 'Content-Type': 'application/json' }
    if (authToken) {
      headers.Authorization = `Bearer ${authToken}`
    }
    return headers
  }, [authToken])

  useEffect(() => {
    let cancelled = false

    const syncAuth = async () => {
      const storedToken = window.localStorage.getItem('elephant_auth_token') || ''
      const storedEmail = window.localStorage.getItem('elephant_user_email') || ''
      setAuthToken(storedToken)
      if (storedEmail) {
        setUserEmail(storedEmail)
      }

      try {
        const response = await fetch(`${apiBase}/auth/me`, {
          headers: storedToken ? { Authorization: `Bearer ${storedToken}` } : undefined,
          credentials: 'include',
        })
        if (!response.ok) {
          window.localStorage.removeItem('elephant_user_email')
          window.localStorage.removeItem('elephant_auth_token')
          if (!cancelled) {
            setUserEmail('')
            setAuthToken('')
          }
          return
        }
        const payload = await readJson(response)
        const email = payload.user?.email || ''
        if (!cancelled && email) {
          setUserEmail(email)
          window.localStorage.setItem('elephant_user_email', email)
        }
      } catch {
        if (!storedEmail && !storedToken && !cancelled) {
          setUserEmail('')
          setAuthToken('')
        }
      }
    }

    syncAuth()
    const onFocus = () => syncAuth()
    window.addEventListener('focus', onFocus)
    return () => {
      cancelled = true
      window.removeEventListener('focus', onFocus)
    }
  }, [apiBase])

  const loadTasks = async () => {
    if (!loggedIn) {
      setTasks([])
      setLoadingTasks(false)
      return
    }
    setLoadingTasks(true)
    try {
      const response = await fetch(`${apiBase}/work/tasks`, {
        headers: authHeaders,
        credentials: 'include',
      })
      const payload = await readJson(response)
      if (!response.ok) {
        throw new Error(payload.detail || 'Failed to load tasks')
      }
      setTasks(payload.tasks || [])
    } catch (error) {
      setFeedback(`${copy.errorPrefix}: ${error.message}`)
    } finally {
      setLoadingTasks(false)
    }
  }

  useEffect(() => {
    loadTasks().catch(() => {})
  }, [apiBase, authToken, userEmail])

  useEffect(() => {
    const refreshTasks = () => {
      loadTasks().catch(() => {})
    }
    window.addEventListener('work-tasks-updated', refreshTasks)
    return () => window.removeEventListener('work-tasks-updated', refreshTasks)
  }, [apiBase, authToken, userEmail])

  const submitMessage = async () => {
    if (!loggedIn) {
      setFeedback(copy.loginRequired)
      return
    }
    const message = inputValue.trim()
    if (!message || working) return
    setWorking(true)
    setFeedback('')
    try {
      const response = await fetch(`${apiBase}/work/assistant/message`, {
        method: 'POST',
        headers: authHeaders,
        credentials: 'include',
        body: JSON.stringify({
          session_id: sessionId || undefined,
          message,
          language,
        }),
      })
      const payload = await readJson(response)
      if (!response.ok) {
        throw new Error(payload.detail || 'Failed to create task draft')
      }
      setSessionId(payload.session_id || '')
      setAssistantMessage(payload.assistant_message || '')
      setDraftTask(payload.draft_task || null)
      setNeedsConfirmation(Boolean(payload.needs_confirmation))
      setInputValue('')
    } catch (error) {
      setFeedback(`${copy.errorPrefix}: ${error.message}`)
    } finally {
      setWorking(false)
    }
  }

  const confirmTask = async () => {
    if (!sessionId || !draftTask) {
      setFeedback(copy.missingDraft)
      return
    }
    setWorking(true)
    setFeedback('')
    try {
      const response = await fetch(`${apiBase}/work/tasks/confirm`, {
        method: 'POST',
        headers: authHeaders,
        credentials: 'include',
        body: JSON.stringify({ session_id: sessionId }),
      })
      const payload = await readJson(response)
      if (!response.ok) {
        throw new Error(payload.detail || 'Failed to confirm task')
      }
      setFeedback(copy.confirmed)
      setAssistantMessage('')
      setDraftTask(null)
      setNeedsConfirmation(false)
      setSessionId('')
      await loadTasks()
    } catch (error) {
      setFeedback(`${copy.errorPrefix}: ${error.message}`)
    } finally {
      setWorking(false)
    }
  }

  const cancelTask = async (taskId) => {
    if (!taskId) return
    try {
      const response = await fetch(`${apiBase}/work/tasks/${taskId}/cancel`, {
        method: 'POST',
        headers: authHeaders,
        credentials: 'include',
      })
      const payload = await readJson(response)
      if (!response.ok) {
        throw new Error(payload.detail || 'Failed to cancel task')
      }
      setTasks((previous) => previous.filter((task) => task.id !== taskId))
    } catch (error) {
      setFeedback(`${copy.errorPrefix}: ${error.message}`)
    }
  }

  return (
    <div className="workspace-view active work-view">
      <section className="work-shell">
        <div className="agent-kicker">{copy.kicker}</div>
        <div className="work-header">
          <div>
            <h2 className="work-title">{copy.title}</h2>
            <p className="work-subtitle">{copy.subtitle}</p>
          </div>
        </div>

        {!loggedIn ? <div className="work-login-state">{copy.loginRequired}</div> : null}

        <div className="work-composer">
          <input
            type="text"
            value={inputValue}
            onChange={(event) => setInputValue(event.target.value)}
            placeholder={copy.inputPlaceholder}
            disabled={!loggedIn || working}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                submitMessage()
              }
            }}
          />
          <button type="button" onClick={submitMessage} disabled={!loggedIn || working}>
            {working ? copy.drafting : copy.send}
          </button>
        </div>

        {assistantMessage ? (
          <div className="work-assistant-card">
            <div className="work-assistant-label">{copy.assistant}</div>
            <p>{assistantMessage}</p>
          </div>
        ) : null}

        {draftTask ? (
          <div className="work-draft-card">
            <div className="work-draft-main">
              <div className="work-draft-title">{draftTask.title || draftTask.summary_text}</div>
              <div className="work-draft-meta">
                <span>{draftTask.asset_symbol}</span>
                <span>{operatorLabel(draftTask.operator, language)}</span>
                <span>{draftTask.threshold_value} {draftTask.threshold_currency}</span>
                <span>{draftTask.recipient_email}</span>
              </div>
            </div>
            {needsConfirmation ? (
              <button type="button" onClick={confirmTask} disabled={working}>
                {copy.confirm}
              </button>
            ) : null}
          </div>
        ) : null}

        {feedback ? <div className="work-feedback">{feedback}</div> : null}

        <div className="work-task-section">
          <div className="work-section-title">{copy.activeTasks}</div>
          {loadingTasks ? <div className="work-empty">{copy.loading}</div> : null}
          {!loadingTasks && !tasks.length ? <div className="work-empty">{copy.noTasks}</div> : null}
          {!loadingTasks && tasks.length ? (
            <div className="work-task-list">
              {tasks.map((task) => (
                <article className="work-task-row" key={task.id}>
                  <div className="work-task-copy">
                    <div className="work-task-title">{task.title}</div>
                    <div className="work-task-meta">
                      <span>{task.asset_symbol}</span>
                      <span>{operatorLabel(task.operator, language)}</span>
                      <span>{task.threshold_value} {task.threshold_currency}</span>
                      <span>{task.recipient_email}</span>
                    </div>
                    {task.last_error ? <div className="work-task-error">{task.last_error}</div> : null}
                  </div>
                  <button type="button" className="work-cancel-btn" onClick={() => cancelTask(task.id)}>
                    {copy.cancel}
                  </button>
                </article>
              ))}
            </div>
          ) : null}
        </div>
      </section>
    </div>
  )
}
