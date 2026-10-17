<h1 align="center">Hi, I'm Hemang Varshney 👋</h1>

<p align="center">
  Software developer working across quant finance, real-time systems, and AI tooling.<br>
  I write code; occasionally it works.
</p>

<p align="center"><img src="assets/divider.svg" width="820" alt=""></p>

## 🏆 Featured work

Most of my repos are experiments. These are the ones I'd defend in a review.

| Project | What it is | Why it's here |
|---|---|---|
| **[limit-order-book](https://github.com/hemv-857/limit-order-book)** | Deterministic limit order book & matching engine in C++20 | No locks on the hot path; determinism is tested, not hoped for |
| **[svi-scanner](https://github.com/hemv-857/svi-scanner)** | SVI volatility-surface fitter that scans Deribit options for arbitrage | Fits a surface, then looks for where it disagrees with the market |
| **[cognitive-convergence-detector](https://github.com/hemv-857/cognitive-convergence-detector)** | Detects when institutional signals converge — crowded positioning / systemic risk | Correlation as an early-warning signal, not dashboard decoration |
| **[mcp-vetter-agent](https://github.com/hemv-857/mcp-vetter-agent)** | AI agent that audits MCP servers before you connect to them | Because I hand agents real tools, so I check what's on the other end |
| **[edge-mem](https://github.com/hemv-857/edge-mem)** | Offline-first edge knowledge engine, Qdrant-backed cloud federation | Works with the network off, and still finds things |
| **[Codeinsight](https://github.com/hemv-857/Codeinsight)** | Ask questions about any repo in plain English; see the architecture it infers | RAG + knowledge graph over code, with the graph drawn out |

<details>
<summary><b>The rest of the portfolio — 26 repos, grouped by what they're actually for</b></summary>

**Quant &amp; market microstructure**

| Repo | What it does |
|---|---|
| [lob-engine](https://github.com/hemv-857/lob-engine) | Price-time priority LOB in Rust, std-only — plus TWAP/VWAP/POV execution algorithms |
| [hawkes-lob](https://github.com/hemv-857/hawkes-lob) | Hawkes process model — tests whether BTC trades self-excite like order books do |
| [rmt-covariance](https://github.com/hemv-857/rmt-covariance) | Covariance cleaning via Random Matrix Theory vs Ledoit-Wolf, with walk-forward backtests |
| [rbergomi-engine](https://github.com/hemv-857/rbergomi-engine) | Rough-volatility pricing — Monte Carlo with control variates, calibrated to live SPX options |
| [151-trading-strats](https://github.com/hemv-857/151-trading-strats) | 151 strategies across 18 asset classes; based on Kakushadze &amp; Serur (2018) |
| [market-pipeline](https://github.com/hemv-857/market-pipeline) | Binance WebSocket → Redis → FastAPI, 35 ms end to end |

**AI tooling &amp; agents**

| Repo | What it does |
|---|---|
| [intellex](https://github.com/hemv-857/intellex) | Natural-language requests → clean, source-backed datasets |
| [vizql](https://github.com/hemv-857/vizql) | Visual SQL explainer — watch a query execute step by step |
| [vizarch](https://github.com/hemv-857/vizarch) | System architecture diagrams from plain English, as SVG |
| [commit-archaeology](https://github.com/hemv-857/commit-archaeology) | Commit history → feature eras, who broke what, and the bus factor |
| [dependency-time-machine](https://github.com/hemv-857/dependency-time-machine) | Any repo + any past date → that project's snapshot, plus what shipped since |
| [impact-lens](https://github.com/hemv-857/impact-lens) | Impact &amp; sustainability media analysis, before/after comparison |
| [J.A.R.V.I.S](https://github.com/hemv-857/J.A.R.V.I.S) | Finds issues matching your skills, plans the contribution, drafts the PR |

**F1 — a three-part series**

| Repo | What it does |
|---|---|
| [predictive-tire-engine](https://github.com/hemv-857/predictive-tire-engine) | Tire degradation predictor, D3 dashboard, live telemetry |
| [f1-performance-intelligence](https://github.com/hemv-857/f1-performance-intelligence) | Telemetry dashboard with an AI race engineer |
| [apex-racing-live-strategy](https://github.com/hemv-857/apex-racing-live-strategy) | Race strategy simulator — tire/fuel modelling, pit optimisation |

**Fintech**

| Repo | What it does |
|---|---|
| [ptm-recovery-agent](https://github.com/hemv-857/ptm-recovery-agent) | Recovers failed Paytm payments, measuring true incremental lift |
| [rzp-recovery-agent](https://github.com/hemv-857/rzp-recovery-agent) | Same for Razorpay — causal, not just "recovered count" |

**Platforms, native &amp; utilities**

| Repo | What it does |
|---|---|
| [ORION](https://github.com/hemv-857/ORION) | Geopolitical risk dashboard — energy supply chains and conflicts, real time |
| [textdistance-rs](https://github.com/hemv-857/textdistance-rs) | Rust port of textdistance — 43 algorithms, 77–1788× faster than Python |
| [agent-office-app](https://github.com/hemv-857/agent-office-app) | macOS SwiftUI app running multiple AI agents — streaming, cost, task queues |
| [PRESENT](https://github.com/hemv-857/PRESENT) | macOS menubar attendance tracker — safe-skip maths and lecture reminders |
| [FinCortex_Finvigators](https://github.com/hemv-857/FinCortex_Finvigators) | AI CFO assistant — spend, cashflow forecasting, planning |
| [Projects](https://github.com/hemv-857/Projects) | Experiments in probability calibration, decision theory, betting |
| [internship-tracker](https://github.com/hemv-857/internship-tracker) | Scrapes 270+ companies, daily digests via Telegram |

</details>


## 🌱 Upstream contributions

Greenfield repos are the easy part. Pushing on someone else's repo is the part I'm proudest of:

- **[jaegertracing/jaeger#9820](https://github.com/jaegertracing/jaeger/pull/9820)** — separate ACP prompt blocks with a delimiter in the AI sidecar
- **[topoteretes/cognee-community#202](https://github.com/topoteretes/cognee-community/pull/202)** — Raindrop.io data-source connector
- **[jankrepl/deepdow#152](https://github.com/jankrepl/deepdow/pull/152)** — `__sub__` / `__rsub__` on the `Loss` class

<p align="center"><img src="assets/divider.svg" width="820" alt=""></p>

<h2 align="center">📈 Live: my chances of getting hired</h2>

<!--HIRE_EXCHANGE:START-->
<div align="center">

<img src="assets/ticker.svg?v=e154c4eb" alt="Hire probability 11.80% (analyst rating: HOLD). 464 commits in 18 sessions · 26/day · never missed a day. Streak: 8." width="640">

</div>

<br>

*18 sessions · 83% hit rate · best streak 8 · 7 exact / 4 near / 4 beat / 3 miss*

> 📊 2026-09 earnings report: 1 session, 0% hit rate, probability -0.2pts. The alpha is imaginary but the vibes are quarterly-confirmed.

| Date (IST) | Forecast | Shipped | Result | Δ pts | Hire probability |
|---|:-:|:-:|---|:-:|:-:|
| **2026-10-18** (today) | 3–62 | ⏳ | Market open | | |
| 2026-10-17 | 3–62 | 2 | 🟢 Near hit | +0.53 | 11.80% |
| 2026-10-16 | 3–62 | 4 | ✅ Exact hit | +0.56 | 11.27% |
| 2026-10-15 | 4–62 | 3 | 🟢 Near hit | +0.55 | 10.71% |
| 2026-10-14 | 4–62 | 3 | 🟢 Near hit | +0.45 | 10.16% |
| 2026-10-13 | 4–11 | 62 | 🚀 Beat | +1.80 | 9.71% |
| 2026-10-12 | 4–11 | 175 | 🚀 Beat | +1.70 | 7.91% |
| 2026-10-11 | 4–15 | 8 | ✅ Exact hit | +0.63 | 6.21% |
| 2026-10-10 | 4–28 | 4 | ✅ Exact hit | +0.14 | 5.58% |
| 2026-10-09 | 7–38 | 4 | ❌ Miss | -0.15 | 5.44% |
| 2026-10-08 | 4–38 | 7 | ✅ Exact hit | +0.18 | 5.59% |
| 2026-10-07 | 11–43 | 3 | ❌ Miss | -0.25 | 5.41% |
| 2026-10-06 | 15–43 | 11 | ❌ Miss | +0.25 | 5.66% |
| 2026-10-05 | 11–43 | 15 | ✅ Exact hit | +0.85 | 5.41% |
| 2026-10-04 | 11–43 | 28 | ✅ Exact hit | +1.05 | 4.56% |

<details>
<summary>How does this work? (a.k.a. why is this in my README)</summary>

- Every day at 00:05 IST a GitHub Action **forecasts a range** for the day: the 7 day trailing window, trimmed — the smallest and largest are dropped, so one monster day can’t turn every forecast into a shrug. It lands about half the time.
- Counts are the commits that still exist on my repos' default branches, so `git log` agrees with me. GitHub's contribution graph never retracts a commit — rebased and amended work stays counted forever, and it claimed 74 for a day with 38 commits in it.
- The next midnight it fetches my **real** commit count and settles the trade.
- Points follow the work: **0** for a day with no commits, up to **1** for matching the top of the range, and up to **1.5** for beating it. Streaks add a small bonus.
- Landing inside the range is a hit, 1 under is a near miss, further under is **-0.25**, and no commits on a day that expected work is **-0.5**.
- Shipping more is never punished. Beating the top of the range is the best possible day, and the score keeps climbing with the overshoot.
- Market manipulation means one thing only: 10+ commits within 60 minutes **in this profile repo** — the only way to game the contribution graph. Overachieving a low forecast across real repos is not a crime. Penalty: **-1.5** pts.
- **Visitors:** 👍/👎 on today's [voting issue](https://github.com/hemv-857/hemv-857/issues) to predict whether the bot hits. No prize, just bragging rights.
- **Monthly:** on the 1st, an earnings report summarises the previous month.
- Probability is 100% fiction. The 100% real part: I actually ship code, and I'm actually looking for a job.

</details>
<!--HIRE_EXCHANGE:END-->


<p align="center"><img src="assets/divider.svg" width="820" alt=""></p>

<h2 align="center">🛠 Stack</h2>

<p align="center"><b>Languages</b></p>

<p align="center">
  <img src="https://img.shields.io/badge/TypeScript-3178C6?style=flat-square&amp;logo=typescript&amp;logoColor=white" alt="TypeScript">
  <img src="https://img.shields.io/badge/Python-3776AB?style=flat-square&amp;logo=python&amp;logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/C%2B%2B-00599C?style=flat-square&amp;logo=c%2B%2B&amp;logoColor=white" alt="C++">
  <img src="https://img.shields.io/badge/Rust-DEA584?style=flat-square&amp;logo=rust&amp;logoColor=black" alt="Rust">
  <img src="https://img.shields.io/badge/Shell-4EAA25?style=flat-square&amp;logo=gnubash&amp;logoColor=white" alt="Shell">
</p>

<p align="center"><b>Frameworks &amp; Tools</b></p>

<p align="center">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&amp;logo=fastapi&amp;logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Next.js-000000?style=flat-square&amp;logo=next.js&amp;logoColor=white" alt="Next.js">
  <img src="https://img.shields.io/badge/React-61DAFB?style=flat-square&amp;logo=react&amp;logoColor=black" alt="React">
  <img src="https://img.shields.io/badge/Prisma-2D3748?style=flat-square&amp;logo=prisma&amp;logoColor=white" alt="Prisma">
  <img src="https://img.shields.io/badge/Tailwind-06B6D4?style=flat-square&amp;logo=tailwindcss&amp;logoColor=white" alt="Tailwind CSS">
  <img src="https://img.shields.io/badge/D3.js-F9A03C?style=flat-square&amp;logo=d3.js&amp;logoColor=black" alt="D3.js">
  <img src="https://img.shields.io/badge/Redis-DC382D?style=flat-square&amp;logo=redis&amp;logoColor=white" alt="Redis">
  <img src="https://img.shields.io/badge/PostgreSQL-4169E1?style=flat-square&amp;logo=postgresql&amp;logoColor=white" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/Docker-2496ED?style=flat-square&amp;logo=docker&amp;logoColor=white" alt="Docker">
</p>

<p align="center"><b>AI &amp; Data</b></p>

<p align="center">
  <img src="https://img.shields.io/badge/LLM_%2F_RAG-FF6B6B?style=flat-square" alt="LLM">
  <img src="https://img.shields.io/badge/Qdrant-DC244C?style=flat-square&amp;logo=qdrant&amp;logoColor=white" alt="Qdrant">
  <img src="https://img.shields.io/badge/MCP-9B59B6?style=flat-square" alt="MCP">
  <img src="https://img.shields.io/badge/WebSocket-RealTime-4CAF50?style=flat-square" alt="WebSocket">
</p>

<p align="center"><b>Domains</b></p>

<p align="center">
  <img src="https://img.shields.io/badge/Quant_Finance-Options_%7C_Backtesting_%7C_Microstructure-FFD700?style=flat-square&amp;labelColor=333" alt="Quant Finance">
  <img src="https://img.shields.io/badge/Fintech-Payments_%7C_Risk-26A69A?style=flat-square&amp;labelColor=333" alt="Fintech">
  <img src="https://img.shields.io/badge/Security-Audit_%7C_MCP-f85149?style=flat-square&amp;labelColor=333" alt="Security">
</p>

<p align="center"><img src="assets/divider.svg" width="820" alt=""></p>


## 📫 Reach me

Open to full-time roles — quant, platform, or AI-infrastructure engineering.

- GitHub: [@hemv-857](https://github.com/hemv-857) (you're here)
- Email / LinkedIn: add them to the profile sidebar

Prefer a concrete conversation to a cover letter. Point me at a
matching-engine latency bug or a CI pipeline that takes 40 minutes and
I'll have opinions before the call ends.

## License

[LICENSE](https://github.com/hemv-857/hemv-857/blob/main/LICENSE) — see the file for the full text.

## License

[MIT](https://github.com/hemv-857/hemv-857/blob/main/LICENSE) — applies to the profile README and anything in this repo.
