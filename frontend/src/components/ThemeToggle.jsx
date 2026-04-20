export default function ThemeToggle({ theme, setTheme }) {
  return (
    <div className="theme-toggle" aria-label="Theme toggle">
      <button className={`theme-chip ${theme === 'light' ? 'active' : ''}`} type="button" onClick={() => setTheme('light')}>
        Day
      </button>
      <button className={`theme-chip ${theme === 'dark' ? 'active' : ''}`} type="button" onClick={() => setTheme('dark')}>
        Night
      </button>
    </div>
  )
}
