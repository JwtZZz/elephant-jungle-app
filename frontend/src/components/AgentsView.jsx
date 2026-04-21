const conceptSeeds = [
  { label: 'Concept', value: 'Cult meme launcher with fast narrative loops' },
  { label: 'Ticker', value: '$BOLT' },
  { label: 'Slogan', value: 'Blink once. The jungle already moved.' },
]

const signalRows = [
  { label: 'Heat map', value: 'Meme + AI + jungle mascot' },
  { label: 'Audience', value: 'Crypto Twitter natives, short-form traders' },
  { label: 'Visual', value: 'Pixel mascot, orange ember, low-fi chaos' },
]

const safetyRows = [
  'Avoid celebrity likeness, brand theft, and fake partnership claims.',
  'Frame it as satire or community culture, not guaranteed profit language.',
  'Keep launch steps simulated until legal, chain, and treasury review are done.',
]

function PlaceholderPanel({ kicker, title, copy }) {
  return (
    <section className="agent-card agent-card-placeholder">
      <div className="agent-kicker">{kicker}</div>
      <h3 className="agent-title">{title}</h3>
      <p className="agent-copy">{copy}</p>
    </section>
  )
}

export default function AgentsView() {
  return (
    <div className="workspace-view active">
      <div className="agents-grid">
        <section className="agent-card meme-agent-card">
          <div className="agent-kicker">Meme Lab Agent</div>

          <div className="agent-topline">
            <div>
              <h2 className="agent-hero">Prototype a meme coin idea without turning it into a launch tool.</h2>
              <p className="agent-copy">
                This panel is for concept shaping, narrative testing, visual direction, and safety review. It helps us
                pressure-test whether a meme project is interesting before anything moves on-chain.
              </p>
            </div>

            <div className="agent-score-block">
              <span className="agent-score-label">Viability</span>
              <span className="agent-score-value">78</span>
              <span className="agent-score-note">Playful, sticky, but still needs a cleaner community hook.</span>
            </div>
          </div>

          <div className="agent-section-grid">
            <div className="agent-section">
              <div className="agent-section-kicker">Core idea</div>
              <div className="agent-pill-grid">
                {conceptSeeds.map((item) => (
                  <div className="agent-pill-card" key={item.label}>
                    <span className="agent-pill-label">{item.label}</span>
                    <span className="agent-pill-value">{item.value}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="agent-section">
              <div className="agent-section-kicker">Narrative signals</div>
              <div className="agent-list">
                {signalRows.map((item) => (
                  <div className="agent-list-row" key={item.label}>
                    <span className="agent-list-label">{item.label}</span>
                    <span className="agent-list-value">{item.value}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="agent-footer-grid">
            <div className="agent-footer-panel">
              <div className="agent-section-kicker">Output mock</div>
              <p className="agent-copy">
                Generate name, ticker, tagline, landing copy, launch moodboard, and a simulated token page brief for
                internal review.
              </p>
            </div>

            <div className="agent-footer-panel">
              <div className="agent-section-kicker">Safety review</div>
              <ul className="agent-safety-list">
                {safetyRows.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        <PlaceholderPanel
          kicker="Agent 02"
          title="Signal Watch"
          copy="A future panel for monitoring live meme narratives, hot tags, and creator momentum before a concept gets pushed further."
        />
        <PlaceholderPanel
          kicker="Agent 03"
          title="Launch Filter"
          copy="A future panel for simulated checklist logic, readiness gates, treasury assumptions, and operator review states."
        />
        <PlaceholderPanel
          kicker="Agent 04"
          title="Post Engine"
          copy="A future panel for drafting launch copy, community voice variants, meme captions, and social posting sequences."
        />
      </div>
    </div>
  )
}
