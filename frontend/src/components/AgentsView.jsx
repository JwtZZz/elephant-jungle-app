const COPY = {
  en: {
    title: 'Set the token fields and launch parameters.',
    name: 'Name',
    symbol: 'Symbol',
    description: 'Description',
    twitter: 'Twitter',
    telegram: 'Telegram',
    website: 'Website',
    image: 'Image',
    mintWallet: 'Mint Wallet',
    signerWallet: 'Signer Wallet',
    buyAmount: 'Buy Amount',
    amountMode: 'Amount Mode',
    slippage: 'Slippage %',
    priorityFee: 'Priority Fee',
    pool: 'Pool',
    showName: 'Show Name',
    build: 'Build launch payload',
    save: 'Save preset',
    descriptionPlaceholder: 'Short token story, launch angle, and meme context.',
    imagePlaceholder: 'Token image upload path / URL',
    mintPlaceholder: 'Fresh mint keypair public key',
    signerPlaceholder: 'Funding wallet public key',
    percentage: '% of supply',
    trueLabel: 'True',
    falseLabel: 'False',
  },
  zh: {
    title: '设置代币字段和发币参数。',
    name: '名称',
    symbol: '简称',
    description: '描述',
    twitter: 'Twitter',
    telegram: 'Telegram',
    website: '网站',
    image: '图片',
    mintWallet: 'Mint 钱包',
    signerWallet: '签名钱包',
    buyAmount: '买入数量',
    amountMode: '数量模式',
    slippage: '滑点 %',
    priorityFee: '优先费',
    pool: '池子',
    showName: '显示名称',
    build: '生成发币参数',
    save: '保存预设',
    descriptionPlaceholder: '填写代币简介、发币角度和 meme 叙事。',
    imagePlaceholder: '代币图片上传路径 / URL',
    mintPlaceholder: '新的 mint 公钥',
    signerPlaceholder: '出资钱包公钥',
    percentage: '供应量百分比',
    trueLabel: '是',
    falseLabel: '否',
  },
}

export default function AgentsView({ language }) {
  const copy = COPY[language] || COPY.en

  return (
    <div className="workspace-view active agents-launch-view">
      <div className="agents-launch-shell">
        <div className="launch-builder-head launch-builder-head-simple">
          <div>
            <h2 className="launch-builder-title">{copy.title}</h2>
          </div>
        </div>

        <section className="launch-form-card launch-form-card-compact">
          <div className="launch-form-grid">
            <label className="launch-input-group">
              <span>{copy.name}</span>
              <input type="text" placeholder="Jungle Spark" />
            </label>
            <label className="launch-input-group">
              <span>{copy.symbol}</span>
              <input type="text" placeholder="JSPRK" />
            </label>
            <label className="launch-input-group launch-input-group-wide">
              <span>{copy.description}</span>
              <textarea rows="4" placeholder={copy.descriptionPlaceholder} />
            </label>
            <label className="launch-input-group">
              <span>{copy.twitter}</span>
              <input type="text" placeholder="https://x.com/..." />
            </label>
            <label className="launch-input-group">
              <span>{copy.telegram}</span>
              <input type="text" placeholder="https://t.me/..." />
            </label>
            <label className="launch-input-group">
              <span>{copy.website}</span>
              <input type="text" placeholder="https://..." />
            </label>
            <label className="launch-input-group">
              <span>{copy.image}</span>
              <input type="text" placeholder={copy.imagePlaceholder} />
            </label>
            <label className="launch-input-group">
              <span>{copy.mintWallet}</span>
              <input type="text" placeholder={copy.mintPlaceholder} />
            </label>
            <label className="launch-input-group">
              <span>{copy.signerWallet}</span>
              <input type="text" placeholder={copy.signerPlaceholder} />
            </label>
            <label className="launch-input-group">
              <span>{copy.buyAmount}</span>
              <input type="text" placeholder="0.05" />
            </label>
            <label className="launch-input-group">
              <span>{copy.amountMode}</span>
              <select defaultValue="sol">
                <option value="sol">SOL</option>
                <option value="percentage">{copy.percentage}</option>
              </select>
            </label>
            <label className="launch-input-group">
              <span>{copy.slippage}</span>
              <input type="text" placeholder="10" />
            </label>
            <label className="launch-input-group">
              <span>{copy.priorityFee}</span>
              <input type="text" placeholder="0.003" />
            </label>
            <label className="launch-input-group">
              <span>{copy.pool}</span>
              <select defaultValue="pump">
                <option value="pump">pump</option>
              </select>
            </label>
            <label className="launch-input-group launch-toggle-group">
              <span>{copy.showName}</span>
              <div className="launch-toggle-row">
                <button type="button" className="launch-toggle active">{copy.trueLabel}</button>
                <button type="button" className="launch-toggle">{copy.falseLabel}</button>
              </div>
            </label>
          </div>

          <div className="launch-action-row">
            <button type="button" className="launch-primary-btn">{copy.build}</button>
            <button type="button" className="launch-secondary-btn">{copy.save}</button>
          </div>
        </section>
      </div>
    </div>
  )
}
