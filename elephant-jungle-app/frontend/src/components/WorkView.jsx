import { useEffect, useMemo, useState } from 'react'

const COPY = {
  en: {
    triggerTitle: 'Price Trigger',
    triggerDesc: 'Set a price threshold — when the market hits it, you get an email.',
    cronTitle: 'Scheduled Reports',
    cronDesc: 'Get market updates on a fixed schedule — daily, hourly, or custom.',
    cronComing: 'Coming soon',
    inputPlaceholder: 'e.g. Email me when SUI drops below 1 USD.',
    send: 'Plan',
    confirm: 'Confirm',
    activeTasks: 'Active triggers',
    loginRequired: 'Login required. Work tasks are tied to your account.',
    noTasks: 'No active triggers yet.',
    cancel: 'Cancel',
    drafting: 'Thinking...',
    loading: 'Loading...',
    missingDraft: 'No draft to confirm.',
    confirmed: 'Task created. Monitoring started.',
    assistant: 'Assistant',
    errorPrefix: 'Error',
    cronSample1: 'Every day at 9 AM send BTC price',
    cronSample2: 'Every hour report top 10 coins',
    cronSample3: 'Daily at 8 PM ETH summary',
    cronPlanned: 'Schedule a recurring report',
  },
  zh: {
    triggerTitle: '价格触发',
    triggerDesc: '设定一个价格阈值，市场触及目标时自动发邮件通知你。',
    cronTitle: '定时报告',
    cronDesc: '按固定时间接收行情报告 — 每天、每小时或自定义时间。',
    cronComing: '即将上线',
    inputPlaceholder: '例如：当 SUI 跌破 1 美元就给我发邮件。',
    send: '规划',
    confirm: '确认创建',
    activeTasks: '活动触发',
    loginRequired: '请先登录。Work 任务会绑定到你的账号和邮箱。',
    noTasks: '暂无活动触发任务。',
    cancel: '取消',
    drafting: '正在规划...',
    loading: '加载中...',
    missingDraft: '没有可确认的草稿。',
    confirmed: '任务已创建，监控已启动。',
    assistant: '助手',
    errorPrefix: '错误',
    cronSample1: '每天早上 9 点发 BTC 价格',
    cronSample2: '每小时汇报 Top 10 币种',
    cronSample3: '每晚 8 点发 ETH 总结',
    cronPlanned: '安排定时报告',
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
  const lang = (language || 'en').startsWith('zh') ? 'zh' : 'en'
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
  const [activeTab, setActiveTab] = useState('trigger')

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
      if (storedEmail) setUserEmail(storedEmail)
      try {
        const response = await fetch(`${apiBase}/auth/me`, {
          headers: storedToken ? { Authorization: `Bearer ${storedToken}` } : undefined,
          credentials: 'include',
        })
        if (!response.ok) {
          window.localStorage.removeItem('elephant_user_email')
          window.localStorage.removeItem('elephant_auth_token')
          if (!cancelled) { setUserEmail(''); setAuthToken('') }
          return
        }
        const payload = await readJson(response)
        const email = payload.user?.email || ''
        if (!cancelled && email) {
          setUserEmail(email)
          window.localStorage.setItem('elephant_user_email', email)
        }
      } catch {
        if (!storedEmail && !storedToken && !cancelled) { setUserEmail(''); setAuthToken('') }
      }
    }
    syncAuth()
    const onFocus = () => syncAuth()
    window.addEventListener('focus', onFocus)
    return () => { cancelled = true; window.removeEventListener('focus', onFocus) }
  }, [apiBase])

  const loadTasks = async () => {
    if (!loggedIn) { setTasks([]); setLoadingTasks(false); return }
    setLoadingTasks(true)
    try {
      const response = await fetch(`${apiBase}/work/tasks`, { headers: authHeaders, credentials: 'include' })
      const payload = await readJson(response)
      if (!response.ok) throw new Error(payload.detail || 'Failed to load tasks')
      setTasks(payload.tasks || [])
    } catch (error) {
      setFeedback(`${copy.errorPrefix}: ${error.message}`)
    } finally { setLoadingTasks(false) }
  }

  useEffect(() => { loadTasks().catch(() => {}) }, [apiBase, authToken, userEmail])
  useEffect(() => {
    const refreshTasks = () => { loadTasks().catch(() => {}) }
    window.addEventListener('work-tasks-updated', refreshTasks)
    return () => window.removeEventListener('work-tasks-updated', refreshTasks)
  }, [apiBase, authToken, userEmail])

  const submitMessage = async () => {
    if (!loggedIn) { setFeedback(copy.loginRequired); return }
    const message = inputValue.trim()
    if (!message || working) return
    setWorking(true); setFeedback('')
    try {
      const response = await fetch(`${apiBase}/work/assistant/message`, {
        method: 'POST', headers: authHeaders, credentials: 'include',
        body: JSON.stringify({ session_id: sessionId || undefined, message, language }),
      })
      const payload = await readJson(response)
      if (!response.ok) throw new Error(payload.detail || 'Failed to create task draft')
      setSessionId(payload.session_id || '')
      setAssistantMessage(payload.assistant_message || '')
      setDraftTask(payload.draft_task || null)
      setNeedsConfirmation(Boolean(payload.needs_confirmation))
      setInputValue('')
    } catch (error) {
      setFeedback(`${copy.errorPrefix}: ${error.message}`)
    } finally { setWorking(false) }
  }

  const confirmTask = async () => {
    if (!sessionId || !draftTask) { setFeedback(copy.missingDraft); return }
    setWorking(true); setFeedback('')
    try {
      const response = await fetch(`${apiBase}/work/tasks/confirm`, {
        method: 'POST', headers: authHeaders, credentials: 'include',
        body: JSON.stringify({ session_id: sessionId }),
      })
      const payload = await readJson(response)
      if (!response.ok) throw new Error(payload.detail || 'Failed to confirm task')
      setFeedback(copy.confirmed)
      setAssistantMessage(''); setDraftTask(null); setNeedsConfirmation(false); setSessionId('')
      await loadTasks()
    } catch (error) {
      setFeedback(`${copy.errorPrefix}: ${error.message}`)
    } finally { setWorking(false) }
  }

  const cancelTask = async (taskId) => {
    if (!taskId) return
    try {
      const response = await fetch(`${apiBase}/work/tasks/${taskId}/cancel`, {
        method: 'POST', headers: authHeaders, credentials: 'include',
      })
      const payload = await readJson(response)
      if (!response.ok) throw new Error(payload.detail || 'Failed to cancel task')
      setTasks((prev) => prev.filter((t) => t.id !== taskId))
    } catch (error) {
      setFeedback(`${copy.errorPrefix}: ${error.message}`)
    }
  }

  const thresholdTasks = tasks.filter(t => t.workflow_type !== 'cron_email')
  const cronTasks = tasks.filter(t => t.workflow_type === 'cron_email')

  return (
    <div className="workspace-view active work-view">
      <style>{`
        .work-layout {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 24px;
          padding: 24px 0 0;
          min-height: 0;
          flex: 1;
          align-items: stretch;
        }
        .work-panel {
          background: var(--bg-surface);
          border: 1px solid var(--border-soft);
          border-radius: 12px;
          display: flex;
          flex-direction: column;
          overflow: hidden;
        }
        .work-panel-header {
          padding: 18px 20px 14px;
          border-bottom: 1px solid var(--border-soft);
        }
        .work-panel-header h3 {
          margin: 0 0 4px;
          font-size: 15px;
          font-weight: 600;
          color: var(--text-primary);
        }
        .work-panel-header p {
          margin: 0;
          font-size: 13px;
          color: var(--text-secondary);
          line-height: 1.4;
        }
        .work-panel-body {
          padding: 16px 20px;
          flex: 1;
          display: flex;
          flex-direction: column;
          gap: 12px;
          overflow-y: auto;
        }
        .work-input-row {
          display: flex;
          gap: 8px;
        }
        .work-input-row input {
          flex: 1;
          padding: 10px 14px;
          border: 1px solid var(--border-soft);
          border-radius: 8px;
          background: var(--bg-page);
          color: var(--text-primary);
          font-size: 14px;
          outline: none;
          transition: border-color .15s;
        }
        .work-input-row input:focus {
          border-color: var(--accent);
        }
        .work-input-row input:disabled {
          opacity: .5;
        }
        .work-input-row button {
          padding: 10px 18px;
          border: none;
          border-radius: 8px;
          background: var(--accent);
          color: #fff;
          font-size: 14px;
          font-weight: 500;
          cursor: pointer;
          white-space: nowrap;
          transition: background .15s;
        }
        .work-input-row button:hover:not(:disabled) {
          filter: brightness(1.15);
        }
        .work-input-row button:disabled {
          opacity: .5;
          cursor: not-allowed;
        }
        .work-assistant-bubble {
          background: var(--bg-surface);
          border-radius: 10px;
          padding: 14px 16px;
          font-size: 14px;
          line-height: 1.55;
          color: var(--text-primary);
          border-left: 3px solid var(--accent);
        }
        .work-assistant-bubble .label {
          font-size: 11px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: .04em;
          color: var(--accent);
          margin-bottom: 6px;
        }
        .work-draft-card {
          background: var(--bg-surface);
          border-radius: 10px;
          padding: 14px 16px;
          border: 1px solid var(--border-soft);
        }
        .work-draft-card .draft-title {
          font-weight: 600;
          font-size: 14px;
          margin-bottom: 8px;
          color: var(--text-primary);
        }
        .work-draft-card .draft-tags {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          margin-bottom: 10px;
        }
        .work-draft-card .draft-tag {
          padding: 3px 10px;
          border-radius: 5px;
          font-size: 12px;
          background: var(--bg-page);
          border: 1px solid var(--border-soft);
          color: var(--text-primary);
        }
        .work-draft-card .draft-confirm {
          padding: 8px 18px;
          border: none;
          border-radius: 8px;
          background: var(--accent);
          color: #fff;
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          transition: background .15s;
        }
        .work-draft-card .draft-confirm:hover {
          filter: brightness(1.15);
        }
        .work-status-msg {
          font-size: 13px;
          color: var(--text-secondary);
          padding: 6px 0;
        }
        .work-status-msg.error {
          color: #f85149;
        }
        .work-status-msg.success {
          color: #3fb950;
        }
        .work-task-section {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .work-task-section-title {
          font-size: 12px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: .05em;
          color: var(--text-secondary);
          padding: 4px 0;
        }
        .work-task-item {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 10px 12px;
          border-radius: 8px;
          background: var(--bg-surface);
          border: 1px solid var(--border-soft);
        }
        .work-task-item .task-info {
          display: flex;
          flex-direction: column;
          gap: 3px;
          min-width: 0;
        }
        .work-task-item .task-name {
          font-size: 13px;
          font-weight: 500;
          color: var(--text-primary);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .work-task-item .task-meta {
          display: flex;
          flex-wrap: wrap;
          gap: 4px;
        }
        .work-task-item .task-meta span {
          font-size: 11px;
          padding: 2px 7px;
          border-radius: 4px;
          background: var(--bg-page);
          color: var(--text-secondary);
        }
        .work-task-item .task-cancel {
          padding: 5px 12px;
          border: 1px solid var(--border-soft);
          border-radius: 6px;
          background: transparent;
          color: var(--text-secondary);
          font-size: 12px;
          cursor: pointer;
          transition: all .15s;
          flex-shrink: 0;
        }
        .work-task-item .task-cancel:hover {
          border-color: #f85149;
          color: #f85149;
        }
        .work-empty-state {
          text-align: center;
          padding: 32px 16px;
          color: var(--text-secondary);
          font-size: 13px;
        }
        .work-cron-planned {
          text-align: center;
          padding: 40px 16px;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 16px;
        }
        .work-cron-planned .icon {
          font-size: 32px;
          opacity: .5;
        }
        .work-cron-planned .title {
          font-size: 15px;
          font-weight: 600;
          color: var(--text-primary);
        }
        .work-cron-planned .desc {
          font-size: 13px;
          color: var(--text-secondary);
          line-height: 1.5;
          max-width: 280px;
        }
        .work-cron-planned .samples {
          display: flex;
          flex-direction: column;
          gap: 6px;
          margin-top: 4px;
        }
        .work-cron-planned .samples .sample {
          font-size: 12px;
          color: var(--text-secondary);
          padding: 8px 14px;
          border-radius: 6px;
          background: var(--bg-surface);
          border: 1px dashed var(--border-soft);
          cursor: default;
        }
        .work-login-banner {
          padding: 14px 20px;
          background: var(--bg-surface);
          border-bottom: 1px solid var(--border-soft);
          font-size: 13px;
          color: var(--text-secondary);
          text-align: center;
        }
        .work-loading-dots::after {
          content: '';
          animation: workDots 1.2s steps(4) infinite;
        }
        @keyframes workDots {
          0% { content: ''; }
          25% { content: '.'; }
          50% { content: '..'; }
          75% { content: '...'; }
        }
        /* responsive stack on narrow screens */
        @media (max-width: 860px) {
          .work-layout { grid-template-columns: 1fr; }
        }
      `}</style>

      {/* Tab bar for mobile */}
      <div className="work-tab-bar" style={{
        display: 'none',
      }}>
        <button
          onClick={() => setActiveTab('trigger')}
          style={{
            flex: 1, padding: '10px', border: 'none', background: activeTab === 'trigger' ? 'var(--surface, #161b22)' : 'transparent',
            color: activeTab === 'trigger' ? 'var(--text-primary)' : 'var(--text-secondary)',
            fontWeight: activeTab === 'trigger' ? 600 : 400, cursor: 'pointer', fontSize: 14,
            borderBottom: activeTab === 'trigger' ? '2px solid var(--accent)' : '2px solid transparent',
          }}
        >{copy.triggerTitle}</button>
        <button
          onClick={() => setActiveTab('cron')}
          style={{
            flex: 1, padding: '10px', border: 'none', background: activeTab === 'cron' ? 'var(--surface, #161b22)' : 'transparent',
            color: activeTab === 'cron' ? 'var(--text-primary)' : 'var(--text-secondary)',
            fontWeight: activeTab === 'cron' ? 600 : 400, cursor: 'pointer', fontSize: 14,
            borderBottom: activeTab === 'cron' ? '2px solid var(--accent)' : '2px solid transparent',
          }}
        >{copy.cronTitle}</button>
      </div>

      <div className="work-layout">
        {/* ──────────────── LEFT: Price Trigger ──────────────── */}
        <div className="work-panel">
          <div className="work-panel-header">
            <h3>{copy.triggerTitle}</h3>
            <p>{copy.triggerDesc}</p>
          </div>

          {!loggedIn && <div className="work-login-banner">{copy.loginRequired}</div>}

          <div className="work-panel-body">
            <div className="work-input-row">
              <input
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                placeholder={copy.inputPlaceholder}
                disabled={!loggedIn || working}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitMessage() }
                }}
              />
              <button type="button" onClick={submitMessage} disabled={!loggedIn || working}>
                {working ? copy.drafting : copy.send}
              </button>
            </div>

            {assistantMessage && (
              <div className="work-assistant-bubble">
                <div className="label">{copy.assistant}</div>
                <div>{assistantMessage}</div>
              </div>
            )}

            {draftTask && (
              <div className="work-draft-card">
                <div className="draft-title">{draftTask.title || draftTask.summary_text}</div>
                <div className="draft-tags">
                  {draftTask.asset_symbol && <span className="draft-tag">{draftTask.asset_symbol}</span>}
                  {draftTask.operator && <span className="draft-tag">
                    {operatorLabel(draftTask.operator, language)}
                    {draftTask.threshold_value != null && ` ${draftTask.threshold_value} ${draftTask.threshold_currency || 'USD'}`}
                  </span>}
                  {draftTask.recipient_email && <span className="draft-tag">{draftTask.recipient_email}</span>}
                </div>
                {needsConfirmation && (
                  <button type="button" className="draft-confirm" onClick={confirmTask} disabled={working}>
                    {copy.confirm}
                  </button>
                )}
              </div>
            )}

            {feedback && (
              <div className={`work-status-msg${feedback.startsWith(copy.errorPrefix) ? ' error' : ''}${feedback === copy.confirmed ? ' success' : ''}`}>
                {feedback}
              </div>
            )}

            <div className="work-task-section">
              <div className="work-task-section-title">{copy.activeTasks}</div>
              {loadingTasks && <div className="work-empty-state">{copy.loading}</div>}
              {!loadingTasks && !thresholdTasks.length && <div className="work-empty-state">{copy.noTasks}</div>}
              {!loadingTasks && thresholdTasks.length > 0 && thresholdTasks.map((task) => (
                <div className="work-task-item" key={task.id}>
                  <div className="task-info">
                    <div className="task-name">{task.title}</div>
                    <div className="task-meta">
                      <span>{task.asset_symbol}</span>
                      {task.operator ? <span>{operatorLabel(task.operator, language)} {task.threshold_value} {task.threshold_currency}</span> : <span>{task.cron_expression}</span>}
                      <span>{task.recipient_email}</span>
                      {task.last_price != null && <span>{lang === 'zh' ? '当前' : 'now'}: ${task.last_price}</span>}
                    </div>
                    {task.last_error && <div style={{ fontSize: 11, color: '#f85149', marginTop: 2 }}>{task.last_error}</div>}
                  </div>
                  <button type="button" className="task-cancel" onClick={() => cancelTask(task.id)}>
                    {copy.cancel}
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ──────────────── RIGHT: Scheduled Cron ──────────────── */}
        <div className="work-panel">
          <div className="work-panel-header">
            <h3>{copy.cronTitle}</h3>
            <p>{copy.cronDesc}</p>
          </div>
          <div className="work-panel-body">
            <div className="work-task-section">
              {loadingTasks && <div className="work-empty-state">{copy.loading}</div>}
              {!loadingTasks && cronTasks.length === 0 && (
                <div className="work-cron-planned">
                  <div className="icon">⏰</div>
                  <div className="title">{copy.cronComing}</div>
                  <div className="desc">{copy.cronPlanned}</div>
                  <div className="samples">
                    <div className="sample">{copy.cronSample1}</div>
                    <div className="sample">{copy.cronSample2}</div>
                    <div className="sample">{copy.cronSample3}</div>
                  </div>
                </div>
              )}
              {!loadingTasks && cronTasks.length > 0 && cronTasks.map((task) => (
                <div className="work-task-item" key={task.id}>
                  <div className="task-info">
                    <div className="task-name">{task.title}</div>
                    <div className="task-meta">
                      <span>{task.asset_symbol}</span>
                      <span>{task.cron_expression}</span>
                      <span>{task.recipient_email}</span>
                      {task.last_price != null && <span>{lang === 'zh' ? '当前' : 'now'}: ${task.last_price}</span>}
                    </div>
                    {task.last_error && <div style={{ fontSize: 11, color: '#f85149', marginTop: 2 }}>{task.last_error}</div>}
                  </div>
                  <button type="button" className="task-cancel" onClick={() => cancelTask(task.id)}>
                    {copy.cancel}
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
