const COPY = {
  en: {
    xWatch: 'X Watch',
    social: 'Social commentary',
    finance: 'Finance News',
    latest: 'Latest headlines',
    updated: 'Updated every five hours. The page scroll keeps the full rail visible.',
    fallback: 'Open the source for the full thread or article.',
    source: 'Source',
  },
  zh: {
    xWatch: 'X 动态',
    social: '社交评论',
    finance: '财经新闻',
    latest: '最新标题',
    updated: '每五小时更新一次。跟随页面下拉查看，不再放进单独滚动框。',
    fallback: '打开原文查看完整帖子或文章。',
    source: '来源',
  },
}

function NewsColumn({ title, kicker, items, copy }) {
  return (
    <section className="market-news-card">
      <div className="market-news-kicker">{kicker}</div>
      <div className="market-news-title">{title}</div>
      <div className="market-news-copy">{copy.updated}</div>
      <div className="market-news-list">
        {items.map((item, index) => (
          <a className="market-news-item" href={item.url} target="_blank" rel="noreferrer" key={`${title}-${index}`}>
            <div className="market-news-item-title">{item.title}</div>
            <div className="market-news-item-copy">{item.summary || copy.fallback}</div>
            <div className="market-news-item-meta">
              {item.source || copy.source}
              {item.published_at ? ` · ${item.published_at}` : ''}
            </div>
          </a>
        ))}
      </div>
    </section>
  )
}

export default function NewsPanels({ briefs, language }) {
  const copy = COPY[language] || COPY.en

  return (
    <>
      <NewsColumn title={copy.xWatch} kicker={copy.social} items={briefs.social} copy={copy} />
      <NewsColumn title={copy.finance} kicker={copy.latest} items={briefs.news} copy={copy} />
    </>
  )
}
