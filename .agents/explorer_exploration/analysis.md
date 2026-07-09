# Codebase Exploration & Implementation Analysis

## Executive Summary
The existing codebase implements a basic, single-ticker LangGraph workflow designed to process one asset (defaulting to SPY) through data provider, analyst, evaluator, and risk manager nodes. This design is insufficient for the portfolio-wide requirements of R1–R4. 

To successfully migrate `MemeStocksStrategy`, we must extend the shared graph state (`AgentState`) to support multi-asset operations, implement high-velocity multi-ticker data fetching, design a quantitative screening pipeline, construct a risk manager that enforces deterministic portfolio limits (2% sizing, 1.6x stock exposure, Stop-Loss/Take-Profit liquidations, and drawdown breakers), and establish an execution node that calculates slippage and outputs daily reports.

---

## 1. Current State of the Codebase

### 1.1 State Schema (`core/state.py`)
- **Current Layout**: Represents a single asset execution. Keys like `ticker: str`, `price: float`, `option_chain: Dict[str, Any]`, and `target_legs: Optional[List[Dict[str, Any]]]` are single-asset centric.
- **Gaps**: Lacks fields for a list of screened assets, proposed trades for multiple underlyings, historical implied volatilities, daily starting equity, and accumulated slippage.

### 1.2 Data Ingestion (`agents/data_provider.py`)
- **Current Layout**: Fetches stock prices, SPY 200 SMA, and options chain for a single underlying `state["ticker"]`. Utilizes a Black-Scholes pricing engine fallback if Alpaca credentials are missing.
- **Gaps**: Only supports a single ticker query. Cannot perform sector or market-wide screening. Does not query VIX or XLU.

### 1.3 Screening and Analysis (`agents/analyst.py`)
- **Current Layout**: Invokes Gemini to select a strategy (`BULL_PUT_SPREAD`, `LONG_STOCK`, or `HOLD`) for a single ticker. If Gemini fails (e.g. 503 errors), it defaults to proposing a Bull Put Spread.
- **Gaps**: Cannot process a collection of assets or rank them programmatically by market factors.

### 1.4 Risk Sizing (`agents/risk_manager.py`)
- **Current Layout**: Simulates single-ticker vertical spreads and stock additions. Performs credit spread width validation (premium must be >= 30% of width) and breaches of delta (+/-1000) or margin (80% utilization) via a human-in-the-loop `interrupt`.
- **Gaps**: No programmatic stop-loss (-15%) or take-profit (+33%) portfolio checks. No daily drawdown check (-5%). No deterministic capital allocation (2%) sizing rules.

### 1.5 Execution and Reporting (`agents/executor.py` & `simulation.py`)
- **Current Layout**: `executor.py` contains placeholder code that prints execution logs. `simulation.py` handles the historical day loop and executes stock transactions directly in the simulator loop rather than letting the graph manage them.
- **Gaps**: Slippage is not tracked. Daily summary emails are not sent. Open orders are not canceled after 125 seconds. The simulation loop is decoupled from the actual agent executor.

---

## 2. Proposed Implementation Strategy

### R1: High-Velocity Data Ingestion
1. **Equities Universe Selection**:
   - Define a static list of ~150 highly liquid US equities (e.g., TSLA, AAPL, AMZN, PLTR, AMD, NVDA, etc.) in `agents/data_provider.py` to act as the raw screening candidate pool.
   - Use a single Alpaca API call `api.get_snapshots(tickers)` to query snapshots for all candidate assets simultaneously.
   - Filter assets by price `2.50 <= price <= 350.0`.
   - Calculate dollar volume (`price * volume`), sort in descending order, and select the top 75 equities.
2. **Options Chain Ingestion**:
   - For the selected 75 equities, fetch front-month option chains.
   - Filter for contracts within $\pm 3$ strikes of the underlying's spot price.
   - To optimize speed and avoid REST call delays, implement concurrent fetches using `ThreadPoolExecutor` or `asyncio` for Alpaca option queries, or mathematically generate them using the Black-Scholes engine.
3. **VIX and SPY/XLU Bars**:
   - Query VIX price (if VIX index is unavailable in Alpaca, fetch from a public index or mock it).
   - Fetch 200-day daily historical bars for SPY and XLU.
4. **Mock Fallback and Warning**:
   - Wrap Alpaca API calls in try-except. Toggle `use_mock_data = True` upon failure.
   - Write a clear, prominent warning to stdout:
     ```python
     print("=================================================================")
     print("  WARNING: USING MOCK / SIMULATED MARKET DATA & OPTION CHAINS")
     print("  Reason: Missing or invalid Alpaca API credentials.")
     print("=================================================================")
     ```
5. **State Updates**:
   - Write `screened_assets`, `option_chains`, `vix_price`, `spy_bars`, and `xlu_bars` to the shared state.

### R2: Quantitative Screening & Sentiment Processing
1. **VIX Market Regime Filter**:
   - Read the VIX price. If `vix_price > 20.50`, immediately update the state with `regime = "BEAR"`, `signal = "HOLD"`, `proposed_trades = []`, and halt further analyst/LLM steps.
2. **Implied Volatility (IV) Velocity Screening**:
   - For each of the top 75 underlyings, retrieve the current ATM option implied volatility.
   - Compare it against the historical `previous_iv` snapshot stored in the state:
     - Discard the underlying if `current_iv <= previous_iv`.
     - Update the `previous_iv` snapshot for the next simulation day.
3. **Call/Put Volume Ratio**:
   - Calculate the total Call trade volume and Put trade volume in the selected option strikes for each candidate.
   - Discard the underlying if the `Call / Put` volume ratio is `< 1.10`.
4. **Rank and Select Top 15**:
   - Calculate IV velocity: `velocity = current_iv - previous_iv`.
   - Sort the remaining candidates by `velocity` in descending order.
   - Select the top 15 candidates and store them as `screened_candidates`.
5. **Analyst LLM Proposal**:
   - Submit the top 15 screened candidates to the Gemini LLM in a single batch request to recommend strategies (`LONG_STOCK`, `BULL_PUT_SPREAD`, or `HOLD`) and offsets.
   - Write the recommendations to `proposed_trades` in the shared state.

### R3: Risk Sizing & Portfolio Guardrails
1. **Deterministic Sizing (2% Rule)**:
   - For each proposed trade in `proposed_trades`:
     - Sizing capital = `portfolio_equity * 0.02`.
     - **Stock position**: `shares = int(sizing_capital / price)`.
     - **Option vertical spread**: `contracts = int(sizing_capital / ((width - net_credit) * 100))`.
2. **Stock Exposure Limit (1.6x)**:
   - Calculate total stock exposure of the simulated portfolio (existing stock value + new stock purchases).
   - If exposure exceeds `1.6 * portfolio_equity`, scale down the new stock order sizes or reject the lower-ranked stock purchases.
3. **Inventory Stop-Loss / Take-Profit (SL/TP)**:
   - Calculate the unrealized gain/loss percentage of all items in `portfolio_inventory`.
   - If any position shows a loss `loss <= -15%` or a gain `gain >= +33%`, mark it for immediate liquidation and execute closing orders.
4. **Intraday Drawdown Breaker (-5%)**:
   - Compare current `portfolio_equity` with `start_of_day_equity`.
   - If drawdown is `<= -5%`, trigger emergency liquidation of all positions, set `portfolio_inventory = []`, and set the regime to `BEAR`.
5. **Order Age Check**:
   - Prior to execution or during cleanup, cancel any open orders that have been unfilled for $> 125$ seconds.

### R4: Execution & Post-Trade Reporting
1. **Alpaca REST Orders**:
   - Submit orders using Alpaca REST API or run mock execution if Alpaca credentials are invalid.
2. **Slippage Calculation**:
   - Calculate trade-level slippage: `slippage = abs(filled_price - prior_price) * quantity` (scaled by 100 for option contracts).
   - Accumulate into `daily_slippage` state.
3. **Daily Summary Report**:
   - Format a Daily Summary Report containing:
     - Daily P&L %
     - Open position count
     - Cash balance
     - Total daily accumulated slippage
   - Print the summary to the console and attempt to email it via SMTP (fall back to log output if SMTP keys are missing).

---

## 3. Recommended Code Modifications

### 3.1 State Schema (`core/state.py`)
Add the following fields:
```python
    vix_price: float
    regime: str  # "BULL" or "BEAR"
    proposed_trades: List[Dict[str, Any]]
    screened_candidates: List[str]
    previous_iv: Dict[str, float]
    start_of_day_equity: float
    daily_slippage: float
    liquidations: List[Dict[str, Any]]
```

### 3.2 Simulation Loop (`simulation.py`)
Modify the simulation loop so it passes portfolio state dynamically from one day to the next, rather than executing mock stock transactions inside the simulation script. The LangGraph agent should control the portfolio cash, inventory, and logic.
