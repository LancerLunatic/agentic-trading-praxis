## 2026-07-08T19:59:24Z
Implement Milestone 2: High-Velocity Ingestion in `agents/data_provider.py`.

Requirements:
1. Normalize and validate input ticker:
   - Handle ticker input (unpack list if passed as list).
   - Strip whitespace and convert to uppercase.
   - Raise `ValueError` if the ticker is empty or invalid (e.g., whitespace only).
2. Toggle mock/simulated fallback:
   - Detect if Alpaca credentials (`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`) are missing or contain placeholders (like "your_alpaca").
   - If missing/invalid, print the warning verbatim to stdout:
     =================================================================
       WARNING: USING MOCK / SIMULATED MARKET DATA & OPTION CHAINS
       Reason: Missing or invalid Alpaca API credentials.
     =================================================================
   - Set mock price = 420.0 if not already provided in state.
3. Ingestion SPY 200 SMA:
   - Query SPY daily historical bars (200 limit) using Alpaca REST API.
   - Calculate the mean of the close prices to populate `spy_200_sma`.
   - Fall back to 405.0 if mock or API fails.
4. Option Chain Ingestion & Fallback:
   - Attempt to GET options snapshot from `https://data.alpaca.markets/v1beta1/options/snapshots/{ticker}`.
   - Parse bid, ask, price, and greeks (delta, gamma, theta, vega, iv) into `option_chain`.
   - If the request fails, OR if the snapshots dict in the response is empty, fall back to generating option chain mathematically using the Black-Scholes engine.
5. Price Boundary Filter:
   - Filter tickers by price bounds: $2.50 <= price <= $350.00.
   - Ensure the current `ticker` is added to `screened_candidates` if its price is within the bounds, and removed/excluded if outside the bounds.
   - To support the candidate universe requirement, also populate `screened_candidates` with a collection of liquid tickers (like AAPL, MSFT, TSLA, etc.) that pass the price filter (when running in mock mode, populate with a list of default mock tickers to ensure downstream nodes have candidates).
6. Ingestion VIX and SPY/XLU:
   - Ingestion VIX price (default to 15.0 or `state.get("vix_price")` if query fails).
   - Ingestion SPY and XLU daily historical bars.

Verify your changes by running pytest:
```powershell
set GOOGLE_API_KEY=mock
venv\Scripts\python.exe -m pytest tests/test_tier1_feature_coverage.py -k "data_provider"
venv\Scripts\python.exe -m pytest tests/test_tier2_boundary_corner.py -k "data_provider"
```
Ensure all 10 data provider tests pass.
Document your implementation, changes, and verification commands/results in `.agents/worker_m2/handoff.md`.
