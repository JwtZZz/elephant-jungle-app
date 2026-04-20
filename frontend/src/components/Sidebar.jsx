const NAV_ITEMS = [
  { key: 'markets', label: 'Markets', index: '01' },
  { key: 'overview', label: 'Overview', index: '02' },
  { key: 'policy', label: 'Policy', index: '03' },
  { key: 'projects', label: 'Projects', index: '04' },
  { key: 'research', label: 'Research', index: '05' },
]

export default function Sidebar({ activeView, onSelect }) {
  return (
    <aside className="workspace-sidebar">
      <div className="brand-mark">
        <div>
          <div className="brand-title">Elephant Jungle</div>
        </div>
        <span className="status-dot" aria-hidden="true" />
      </div>

      <div className="nav-list">
        {NAV_ITEMS.map((item) => (
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
