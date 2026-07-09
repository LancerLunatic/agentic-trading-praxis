## 2026-07-08T20:06:53Z
You are a Worker subagent.
Your directory is: c:/Users/apoll/Documents/agentic-trading-praxis/.agents/worker_m3

Objective:
Implement Milestone 3: Quant Screening & Sentiment Processing in `agents/analyst.py`.

Requirements:
1. VIX regime check:
   - Check `vix_price` in the state.
   - If `vix_price > 20.50` (specifically `vix_price > 20.50`), update regime to `"BEAR"`, set `signal = "HOLD"`, clear/empty `proposed_trades` and `target_legs`, and return.
   - Make sure that for `vix_price <= 20.50`, the regime remains `"BULL"` (or whatever it was) and does not halt.
2. Call/Put volume ratio constraint:
   - If `call_put_ratio` is in the state and is `< 1.10`, set `signal = "HOLD"` and return.
3. IV velocity screening:
   - For a given ticker, calculate IV velocity as `current_iv - previous_iv`.
   - ATM option IV is the implied volatility of the option with strike closest to the ticker price.
   - Discard the underlying if IV velocity is stagnant or decreased (`current_iv <= previous_iv`).
   - If discarded, set `signal = "HOLD"`.
4. Candidate ranking:
   - For all tickers in `screened_candidates`, calculate their IV velocity using ATM option IV and `previous_iv`.
   - Discard any candidate with velocity <= 0.
   - Rank the remaining candidates by absolute IV velocity in descending order, and select the top 15.
   - Output the ranked candidate tickers to `ranked_candidates` in the returned state.
   - Update `previous_iv` in the state with the current IVs of the candidates.
5. LLM proposal:
   - If `signal` is not `"HOLD"`, invoke the ChatGoogleGenerativeAI model to suggest the strategy for the primary ticker, parsing `signal`, `strategy`, `strike_offset_short`, `strike_offset_long`, and `reason` from the JSON response.
   - Construct `target_legs` and update the recommendation list `analysis_recs`.
   - Handle LLM exceptions and invalid JSON responses gracefully using a default fallback (e.g. `BUY` `BULL_PUT_SPREAD`).

Verify your changes by running pytest:
```powershell
set GOOGLE_API_KEY=mock
venv\Scripts\python.exe -m pytest tests/test_tier1_feature_coverage.py -k "analyst"
venv\Scripts\python.exe -m pytest tests/test_tier2_boundary_corner.py -k "analyst"
```
Ensure all 10 analyst tests pass.
Document your implementation, changes, and verification commands/results in `.agents/worker_m3/handoff.md`.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.
