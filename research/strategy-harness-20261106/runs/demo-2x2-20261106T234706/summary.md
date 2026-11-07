# 批量评估 demo-2x2-20261106T234706

- 区间：2025-01-02 .. 2026-11-06（交易日 446 个）
- 折：3 个，使用 fold#0
- 标的池：even_stride n=200
- data_generation：`2b948c890e75472ab8317ca0ce40af77` → stable=True
- 共享装载：prepare 5.1s / run 3.8s / 每 trial 摊销 427.7ms
- 峰值 RSS：988.7MB，墙钟 29.9s

| trial | 策略 | 窗口 | 成本档 | 收益 | 年化 | 最大回撤 | Sharpe | 交易数 | 命中缓存 | PSR(DSR) | n_trials | EM | BH q |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| t0001 | first_limit_pullback_3f_runner_t74 | IS | zero | -0.0747 | -0.0752 | -0.2795 | -0.26 | 140 | Y | 0.0000 | 4 | 0.842 | 1.000 |
| t0002 | first_limit_pullback_3f_runner_t74 | IS | real | -0.1076 | -0.1084 | -0.2963 | -0.42 | 141 | Y | 0.0000 | 4 | 0.842 | 1.000 |
| t0003 | first_limit_pullback_3f_runner_t74 | OOS | zero | -0.0526 | -0.203 | -0.1448 | -0.84 | 39 | Y | 0.0000 | 4 | 1.432 | 1.000 |
| t0004 | first_limit_pullback_3f_runner_t74 | OOS | real | -0.0648 | -0.2452 | -0.1502 | -1.08 | 39 | Y | 0.0000 | 4 | 1.432 | 1.000 |
| t0005 | first_limit_pullback_3f_runner_t74 | ALL | zero | -0.1981 | -0.1173 | -0.3949 | -0.41 | 267 | Y | 0.0000 | 4 | 0.789 | 1.000 |
| t0006 | first_limit_pullback_3f_runner_t74 | ALL | real | -0.2583 | -0.1553 | -0.4264 | -0.59 | 269 | Y | 0.0000 | 4 | 0.789 | 1.000 |
| t0007 | first_board_chain_rebreak | IS | zero | -0.266 | -0.2678 | -0.3258 | -1.68 | 41 | Y | 0.0000 | 4 | 0.842 | 1.000 |
| t0008 | first_board_chain_rebreak | IS | real | -0.2777 | -0.2796 | -0.3347 | -1.76 | 41 | Y | 0.0000 | 4 | 0.842 | 1.000 |
| t0009 | first_board_chain_rebreak | OOS | zero | -0.1288 | -0.4395 | -0.1498 | -3.26 | 12 | Y | 0.0000 | 4 | 1.432 | 1.000 |
| t0010 | first_board_chain_rebreak | OOS | real | -0.1326 | -0.4497 | -0.1534 | -3.36 | 12 | Y | 0.0000 | 4 | 1.432 | 1.000 |
| t0011 | first_board_chain_rebreak | ALL | zero | -0.4532 | -0.289 | -0.4743 | -1.74 | 87 | Y | 0.0000 | 4 | 0.789 | 1.000 |
| t0012 | first_board_chain_rebreak | ALL | real | -0.4716 | -0.3026 | -0.4915 | -1.84 | 87 | Y | 0.0000 | 4 | 0.789 | 1.000 |

> PSR 即已对 EM 校正的 deflated Sharpe（stats_v2.deflated_sharpe_psr，偏度/峰度按正态假设代入，`moment_source` 逐条标注）；BH q 为该窗口内跨试验的 Benjamini-Hochberg q 值，n_trials = 该窗口成功试验数（策略×成本档）。
