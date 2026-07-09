## 2026-07-09T00:36:07Z
Objective:
Remediate the four specific integrity violations identified during the Forensic Audit:

1. Dynamic Candidate Selection (R1 Ingestion):
   In `agents/data_provider.py`, replace the static list of 8 hardcoded stocks with a dynamic selection of the top 75 liquid equities.
   - Define a list of at least 90-100 well-known liquid tickers (e.g., AAPL, MSFT, TSLA, NVDA, AMZN, NFLX, META, GOOGL, AMD, INTC, MS, GS, JPM, BAC, WFC, C, COF, AXP, V, MA, PYPL, SQ, QQQ, SPY, IWM, DIA, XLE, XLF, XLK, XLY, XLP, XLI, XLU, XLV, XLB, and other highly active equities).
   - If not in mock mode, query daily historical bars for these tickers to calculate their daily dollar volume (Close Price * Volume), sort them in descending order, filter them by price bounds ($2.50 <= price <= $350.00), and select the top 75.
   - If in mock mode, simulate this logic dynamically by assigning simulated price and volume to each of the 90-100 tickers, sorting by simulated dollar volume, filtering by price, and selecting the top 75.

2. Candidate Option Chains & Screening:
   Ensure option chains are fetched or generated for ALL 75 screened candidates, not just the primary ticker.
   - In `data_provider_node`, if use_mock_data is True (or if live options fetching fails/not configured), loop through all tickers in `screened_candidates` and generate their mock option chains using the Black-Scholes generator, storing all generated option legs in the `option_chain` state parameter.
   - This ensures the analyst node can calculate ATM IV and IV velocity for all candidates, making the QUANT SCREENING and candidate ranking logic fully functional.

3. Eliminate Pre-populated Portfolio Facade:
   In `agents/data_provider.py`, remove the pre-population block that initializes a complex portfolio inventory out of thin air if `portfolio_inventory` is empty. The simulation should start with an empty portfolio (`portfolio_inventory = []`) and only acquire positions dynamically when the executor node processes approved signals.

4. Bypassed Execution & Loss of Proceeds on Risk Events:
   Fix the bypassed execution of liquidations when `user_approved` is False:
   - In `main.py`, update the router function to route to `"execute_trade"` if `user_approved` is True OR if there are any liquidations to execute:
     ```python
     def router(state: AgentState):
         if state.get("user_approved", False) or len(state.get("liquidations", [])) > 0:
             return "execute_trade"
         return END
     ```
   - In `agents/executor.py`, update `execute_trade_node` so that it does not return early when `user_approved` is False if there are liquidations to process. Specifically, it should always process the liquidations first (liquidating positions and adding cash proceeds to the balance), and only skip the proposed trade execution legs if `user_approved` is False or signal is `"HOLD"`.

Verify your changes by running pytest and backtest:
```powershell
set GOOGLE_API_KEY=mock
venv\Scripts\python.exe -m pytest
venv\Scripts\python.exe simulation.py
```
Ensure all tests pass and the backtest simulation runs cleanly with no exceptions.
Document your changes in `.agents/worker_remediation/handoff.md`.
