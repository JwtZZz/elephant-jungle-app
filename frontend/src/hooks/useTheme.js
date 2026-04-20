import { useEffect, useState } from 'react'

const THEME_KEY = 'elephant-jungle-theme'

export function useTheme() {
  const [theme, setTheme] = useState(() => localStorage.getItem(THEME_KEY) || 'light')

  useEffect(() => {
    document.body.dataset.theme = theme
    localStorage.setItem(THEME_KEY, theme)
  }, [theme])

  return { theme, setTheme }
}
