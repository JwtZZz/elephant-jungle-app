function NewsColumn({ title, kicker, items }) {
  return (
    <section className="market-news-card">
      <div className="market-news-kicker">{kicker}</div>
      <div className="market-news-title">{title}</div>
      <div className="market-news-copy">Updated every five hours. Scroll inside this panel to browse the latest items without stretching the whole page.</div>
      <div className="market-news-list">
        {items.map((item, index) => (
          <a className="market-news-item" href={item.url} target="_blank" rel="noreferrer" key={`${title}-${index}`}>
            <div className="market-news-item-title">{item.title}</div>
            <div className="market-news-item-copy">{item.summary || 'Open the source for the full thread or article.'}</div>
            <div className="market-news-item-meta">
              {item.source || 'Source'}
              {item.published_at ? ` 路 ${item.published_at}` : ''}
            </div>
          </a>
        ))}
      </div>
    </section>
  )
}

export default function NewsPanels({ briefs }) {
  return (
    <div className="market-news-grid">
      <NewsColumn title="X Watch" kicker="Social commentary" items={briefs.social} />
      <NewsColumn title="Finance News" kicker="Latest headlines" items={briefs.news} />
    </div>
  )
}
