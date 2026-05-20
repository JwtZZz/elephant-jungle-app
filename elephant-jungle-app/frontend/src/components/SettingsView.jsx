const LANGUAGE_OPTIONS = [
  { key: 'en', label: 'English' },
  { key: 'zh', label: '中文' },
]

const COPY = {
  en: {
    kicker: 'Setting',
    title: 'Language',
    copy: 'Choose the display language for the interface.',
  },
  zh: {
    kicker: '设置',
    title: '语言',
    copy: '选择界面的显示语言。',
  },
}

export default function SettingsView({ language, setLanguage }) {
  const copy = COPY[language] || COPY.en

  return (
    <div className="workspace-view active settings-view">
      <section className="settings-card">
        <div className="agent-kicker">{copy.kicker}</div>
        <h2 className="settings-title">{copy.title}</h2>
        <p className="settings-copy">{copy.copy}</p>

        <div className="settings-option-row">
          {LANGUAGE_OPTIONS.map((option) => (
            <button
              key={option.key}
              type="button"
              className={`settings-chip ${language === option.key ? 'active' : ''}`}
              onClick={() => setLanguage(option.key)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </section>
    </div>
  )
}
