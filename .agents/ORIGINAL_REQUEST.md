# Original User Request

## 2026-07-08T19:47:43Z

Migrate a legacy QuantConnect trading script (`MemeStocksStrategy`) into an asynchronous, multi-agent trading framework using LangGraph, implementing high-velocity data ingestion, quantitative screening, sentiment processing, and risk constraints.

Working directory: c:/Users/apoll/Documents/agentic-trading-praxis
Integrity mode: development

## Requirements

### R1. High-Velocity Data Ingestion
- Identify top 75 equities matching price bounds ($2.50 to $350) and high dollar volume metrics.
- Query front-month option chains for these underlyings, filtering for contracts within $\pm 3$ strikes.
- Fetch VIX price index and SPY/XLU historical ETF daily bars.
- Write raw option chains and VIX price to the shared state.
- Gracefully fall back to simulated mock option chains and VIX index if Alpaca keys are missing or invalid.
- Print a clear, prominent warning message to the human operator (console log) indicating if mock/simulated data is being used due to missing, invalid, or failing Alpaca keys.

### R2. Quantitative Screening & Sentiment Processing
- Read the VIX price. If VIX is above 20.50, flag the market regime as BEAR and halt further screening/trading.
- Calculate ATM Implied Volatility (IV) for each active underlying and compare it to the historical `previous_iv` snapshot. Discard assets where volatility has stagnated or decreased.
- Filter remaining candidates using a Call/Put volume ratio constraint ($\ge 1.10$).
- Rank candidates by absolute IV velocity (increase in IV) and select the top 15 to output as `proposed_trades`.

### R3. Risk Sizing & Portfolio Guardrails
- Enforce a deterministic capital allocation rule: exactly 2% of total portfolio equity per new position.
- Limit total stock exposure to a maximum of 1.6 of portfolio equity.
- Synchronize portfolio inventory. If any active holding shows an unrealized loss $\le -15\%$ or unrealized gain $\ge +33\%$, liquidate it immediately.
- If intra-day portfolio drawdown drops below -5% from start-of-day portfolio value, trigger an emergency liquidation of all positions and set the system regime to BEAR.
- Cancel any open orders that remain unfilled after 125 seconds.

### R4. Execution & Post-Trade Reporting
- Submit orders via the Alpaca REST API (or execute mock orders if Alpaca keys are missing).
- Calculate slippage per trade: compare the raw market price immediately prior to order routing against the actual filled price. Accumulate this into a running daily slippage tracking state.
- Dispatch a Daily Summary Report (console log and email notification via Alpaca/SMTP) containing daily P&L %, open positions count, cash balance, and total accumulated slippage.

---

## Acceptance Criteria

### Verification Mechanism
- Verification will be conducted programmatically using a simulated backtest execution run over a 30-day historical window.

### General Criteria
- [ ] No hardcoded keys; all secrets must be loaded from environment variables or use a mock fallback when missing.
- [ ] Code builds and passes a full backtest simulation run via `simulation.py` with zero unhandled crashes.
- [ ] Data provider successfully queries and handles options chain snapshots and Greeks.
- [ ] Analyst successfully screens and ranks candidates by IV increase and Call/Put ratio.
- [ ] Risk manager enforces stop-loss, take-profit, margin utilization limit, and daily drawdown breakers.
- [ ] Daily summary reports are generated with accurate slippage calculations and cash balances.
