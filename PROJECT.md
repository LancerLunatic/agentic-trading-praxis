# Project: MemeStocksStrategy to LangGraph Migration

## Architecture
The system consists of the following components integrated into a LangGraph workflow:
1. **Data Ingestion Node (`data_provider_node` in `agents/data_provider.py`)**:
   - Queries price and volume snapshots for a candidate universe.
   - Selects the top 75 equities within the price bounds ($2.50 to $350) and high dollar volume.
   - Fetches options chain snapshots within $\pm 3$ strikes, VIX price, and historical bars.
   - Writes option chains, VIX price, and market data to shared state.
   - Toggles mock/simulated fallback if Alpaca credentials are missing/invalid and prints warning.
2. **Screening & Analyst Node (`analyst_node` in `agents/analyst.py`)**:
   - If VIX > 20.50, flags BEAR market regime and halts screening.
   - Compares ATM IV to the historical snapshot `previous_iv`. Discards stagnated/decreased IV assets.
   - Filters by Call/Put ratio constraint ($\ge 1.10$).
   - Ranks candidates by absolute IV velocity and selects the top 15 to output as `proposed_trades` via Gemini batch query.
3. **Risk Manager Node (`risk_manager_node` in `agents/risk_manager.py`)**:
   - Programmatically monitors existing positions in `portfolio_inventory`.
   - Liquidates position immediately on Stop-Loss ($\le -15\%$) or Take-Profit ($\ge +33\%$).
   - Enforces emergency -5% daily drawdown liquidation and sets system to BEAR.
   - Enforces 2% capital sizing per position and a 1.6x total stock exposure limit.
   - Cancels open orders older than 125 seconds.
4. **Executor Node (`execute_trade_node` in `agents/executor.py`)**:
   - Submits execution orders to Alpaca (or mock executor).
   - Computes transaction slippage and accumulates to daily slippage tracking.
   - Dispatches a Daily Summary Report (console log and email notification via SMTP).

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | State Schema Extension | Update AgentState in `core/state.py` with screening lists and portfolio variables | None | DONE |
| 2 | High-Velocity Ingestion (R1) | Batch-fetch market data, filter top 75, query option chains, fetch VIX, SPY/XLU | M1 | DONE |
| 3 | Quant Screening & Analyst (R2) | Implement VIX filter, IV velocity comparison, Call/Put filter, top 15 ranking, LLM proposal | M2 | DONE |
| 4 | Risk & Portfolio Guardrails (R3) | Programmatic position sizing (2%), exposure (1.6x), stop loss/take profit, drawdown breaker, cancel orders | M3 | IN_PROGRESS (by Implementation Track: 18cdffbe-5044-414c-b1c2-b9fc246c1c2d) |
| 5 | Execution, Slippage & Reporting (R4) | Submitting orders, slippage calculation, Daily Summary Report formatting | M4 | IN_PROGRESS (by Implementation Track: 18cdffbe-5044-414c-b1c2-b9fc246c1c2d) |
| 6 | E2E Integration and Simulation | Harmonize `simulation.py` with graph's state and run 30-day simulation backtest | M5 | IN_PROGRESS (by Implementation Track: 18cdffbe-5044-414c-b1c2-b9fc246c1c2d) |

## Interface Contracts
- **`AgentState` Schema**:
  - `vix_price`: float
  - `regime`: str ("BULL" or "BEAR")
  - `screened_candidates`: List[str]
  - `proposed_trades`: List[Dict[str, Any]]
  - `previous_iv`: Dict[str, float]
  - `start_of_day_equity`: float
  - `daily_slippage`: float
  - `liquidations`: List[Dict[str, Any]]
  - `portfolio_inventory`: List[Dict[str, Any]]
  - `cash`: float
  - `portfolio_equity`: float

## Code Layout
- `core/state.py` — Schema definitions.
- `agents/data_provider.py` — Data fetching and mock fallback.
- `agents/analyst.py` — Quantitative screening and LLM trade selection.
- `agents/risk_manager.py` — Risk rules, stop-losses, drawdowns, capital allocation.
- `agents/executor.py` — Order execution, slippage, daily reports.
- `simulation.py` — Backtest runner script.
