const COPY = {
  en: { aria: 'Theme toggle', light: 'Day', dark: 'Night' },
  zh: { aria: '主题切换', light: '白天', dark: '夜间' },
}

export default function ThemeToggle({ theme, setTheme, language }) {
  const copy = COPY[language] || COPY.en

  return (
    <div className="theme-toggle" aria-label={copy.aria}>
      <button className={`theme-chip ${theme === 'light' ? 'active' : ''}`} type="button" onClick={() => setTheme('light')}>
        {copy.light}
      </button>
      <button className={`theme-chip ${theme === 'dark' ? 'active' : ''}`} type="button" onClick={() => setTheme('dark')}>
        {copy.dark}
      </button>
    </div>
  )
}
