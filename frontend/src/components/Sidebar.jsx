import { useRef } from 'react'
import { useSpriteOrbit } from '../hooks/useSpriteOrbit'

const NAV_ITEMS = {
  en: [
    { key: 'markets', label: 'Markets', index: '01' },
    { key: 'agents', label: 'meme pump', index: '02' },
    { key: 'policy', label: 'Tbot', index: '03' },
    { key: 'wallet', label: 'My Wallet', index: '04' },
    { key: 'research', label: 'Setting', index: '05' },
  ],
  zh: [
    { key: 'markets', label: '市场', index: '01' },
    { key: 'agents', label: 'meme pump', index: '02' },
    { key: 'policy', label: 'Tbot', index: '03' },
    { key: 'wallet', label: '我的钱包', index: '04' },
    { key: 'research', label: '设置', index: '05' },
  ],
}

export default function Sidebar({ activeView, onSelect, language }) {
  const items = NAV_ITEMS[language] || NAV_ITEMS.en
  const sidebarSpriteTrackRef = useRef(null)
  const sidebarSpriteShellRef = useRef(null)

  const { spriteMode } = useSpriteOrbit([
    { trackRef: sidebarSpriteTrackRef, shellRef: sidebarSpriteShellRef, direction: 1 },
  ])

  return (
    <aside className="workspace-sidebar">
      <div className="sidebar-pepe-track" ref={sidebarSpriteTrackRef} aria-hidden="true">
        <div className="sprite-shell facing-right" ref={sidebarSpriteShellRef}>
          <div className={`sprite-avatar ${spriteMode}`} />
        </div>
      </div>
      <div className="brand-mark">
        <div>
          <div className="brand-title">Elephant Jungle</div>
        </div>
        <span className="status-dot" aria-hidden="true" />
      </div>

      <div className="nav-list">
        {items.map((item) => (
          <button
            key={item.key}
            className={`nav-item ${activeView === item.key ? 'active' : ''}`}
            type="button"
            onClick={() => onSelect(item.key)}
          >
            <span className="nav-icon">{item.index}</span>
            <span>{item.label}</span>
          </button>
        ))}
      </div>
    </aside>
  )
}
