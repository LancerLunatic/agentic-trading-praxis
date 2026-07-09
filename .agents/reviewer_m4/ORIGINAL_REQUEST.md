## 2026-07-08T16:12:49-04:00
You are a Reviewer subagent.
Your directory is: c:/Users/apoll/Documents/agentic-trading-praxis/.agents/reviewer_m4

Objective:
Review the changes made to `agents/risk_manager.py` for Milestone 4 (Risk Sizing & Portfolio Guardrails).
Verify that:
1. It monitors existing positions and executes STOP_LOSS (<= -15.0%) and TAKE_PROFIT (>= +33.0%) liquidations, appending to `liquidations` and removing from inventory.
2. It monitors daily drawdown and triggers the drawdown breaker if <= -5.0%. Drawdown breaker sets regime to BEAR, sets defensive_cash_mode to True, liquidates all positions, and clears the inventory.
3. It enforces the 2% capital sizing rule for stock and vertical spread trades, scaling down quantities in-place and rejecting if max quantity is 0.
4. It enforces the 1.6x total stock exposure limit, rejecting proposed trades if breached.
5. It cancels open orders older than 125 seconds, appending to `cancelled_orders`.
6. Preserves existing portfolio greeks and margin calculations or custom overrides in `risk_manager_node`.
7. Runs tests:
   ```powershell
   set GOOGLE_API_KEY=mock
   venv\Scripts\python.exe -m pytest tests/test_tier1_feature_coverage.py -k "risk_manager"
   venv\Scripts\python.exe -m pytest tests/test_tier2_boundary_corner.py -k "risk_manager"
   ```
8. Confirm all 10 risk manager tests pass.
9. Output your findings and verdict in `.agents/reviewer_m4/handoff.md`.
