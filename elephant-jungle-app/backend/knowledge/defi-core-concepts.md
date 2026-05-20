---
title: DeFi core concepts
project: DeFi
category: defi
doc_type: reference
language: zh
source: Elephant Jungle Seed
url: seed://web3-foundations/defi-core-concepts
summary: 去中心化金融的核心原语：DEX、借贷、AMM、收益聚合和治理。
---

# 什么是 DeFi

去中心化金融（DeFi）是建立在区块链上的金融应用生态，通过智能合约替代传统金融中介。用户无需银行账户，只需要一个钱包就可以进行借贷、交易、理财等操作。DeFi 的核心是 Permissionless（无需许可）和 Non-custodial（非托管）。

# 去中心化交易所（DEX）

DEX 允许用户直接在链上兑换代币，无需向中心化交易所充值。代表协议是 Uniswap。用户保留资产的控制权，交易通过智能合约自动执行。DEX 的流动性由用户（LP，流动性提供者）提供，LP 赚取交易手续费。

# AMM 自动做市

自动做市商（AMM）是 DEX 的核心机制。传统订单簿需要买卖双方同时存在，而 AMM 通过数学公式（如 Uniswap 的 x*y=k）自动定价。用户和流动性池交易，而不是和其他用户交易。LP 按比例向池子存入两种代币，赚取该池的交易手续费。

# 借贷协议

链上借贷协议（如 Aave、Compound）允许用户存入资产赚取利息，或超额抵押借出资产。利率由资金池利用率通过算法动态调整——借款需求越高，利率越高。清算机制是借贷协议安全的核心：如果抵押物价值跌破清算线，第三方可以清算贷款并获取清算奖励。

# 收益聚合与治理

收益聚合器（如 Yearn）将用户资金自动配置到收益最优的 DeFi 策略中，实现复利优化。治理代币（如 UNI、AAVE）赋予持币者协议参数调整、资金库使用等投票权。DeFi 治理正从纯治理代币投票向委托投票和治理快照等方向演进。
