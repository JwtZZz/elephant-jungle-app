---
title: Layer 2 overview
project: Layer2
category: scaling
doc_type: reference
language: zh
source: Elephant Jungle Seed
url: seed://web3-foundations/layer2-overview
summary: 以太坊 Layer 2 扩展方案的主要类型和工作原理。
---

# 为什么需要 Layer 2

以太坊 Layer 1 的处理能力有限（约 15-30 TPS），拥堵时 Gas 费用飙升。Layer 2 是在 Layer 1 之上构建的扩展方案，将大量交易在链下处理，只将最终结果提交到主链。目标是提升吞吐量、降低费用，同时继承主链的安全性。

# Rollup 方案

Rollup 是目前主流的 Layer 2 方案。它将数百笔交易打包压缩成一个批次，只将压缩后的数据和状态根提交到以太坊主链。Rollup 分为两种：Optimistic Rollup（如 Arbitrum、Optimism）假设交易有效直到被挑战（有 7 天挑战期），ZK Rollup（如 zkSync、StarkNet）用零知识证明在提交时就验证交易的有效性。

# 状态通道

状态通道允许参与者在链下进行多轮交易，只在通道开启和关闭时上链。适合高频小额支付场景（如游戏内支付、微交易）。缺点是参与者需要在通道存在期间一直在线监控。

# Plasma 和 Validium

Plasma 是早期的 Layer 2 方案，将交易数据通过侧链处理，定期向主链提交 Merkle 根。但由于数据可用性问题和退出机制复杂，已逐渐被 Rollup 取代。Validium 类似于 ZK Rollup，但交易数据放在链下（而非主链），安全性低于 Rollup。

# 当前格局

Arbitrum 和 Optimism 在 Optimistic Rollup 领域占据主导地位，各自有庞大的 DeFi 生态。ZK Rollup 方面，zkSync Era 和 StarkNet 正在快速增长。Layer 2 的差异化竞争焦点包括手续费、提款速度（Optimistic 的 7 天等待期 vs ZK 的即时提款）、以及与以太坊主链的兼容性。
