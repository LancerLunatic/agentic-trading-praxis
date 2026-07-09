## 2026-07-08T20:10:09Z

Implement Milestone 4: Risk Sizing & Portfolio Guardrails in `agents/risk_manager.py`.

Requirements:
1. Programmatically monitor existing positions in `portfolio_inventory`:
   - Calculate unrealized return for each position: `(current_price - entry_price) / entry_price` or `(current_price - price) / price`.
   - If a position's return is `<= -0.15` (exactly -15% or worse), trigger immediate Stop-Loss liquidation.
   - If a position's return is `>= 0.33` (exactly +33% or better), trigger immediate Take-Profit liquidation.
   - Create a liquidation entry in `liquidations` list: `{"symbol": pos["symbol"], "reason": "STOP_LOSS" or "TAKE_PROFIT", "quantity": pos["quantity"], "price": pos["current_price"]}`.
   - Remove liquidated positions from `portfolio_inventory`.
2. Enforce intraday drawdown breaker:
   - Check if the daily drawdown: `(portfolio_equity - start_of_day_equity) / start_of_day_equity <= -0.05` (exactly -5% drawdown or worse).
   - If triggered:
     - Set `regime = "BEAR"`.
     - Set `defensive_cash_mode = True`.
     - Liquidate all remaining positions in `portfolio_inventory`, adding them to the `liquidations` list with reason `"DRAWDOWN_BREAKER"` (or similar).
     - Empty/clear `portfolio_inventory = []`.
3. Sizing constraints (2% Capital Rule):
   - If `signal == "BUY"` and a trade is proposed, verify that the total sizing cost does not exceed 2% of `portfolio_equity`:
     - Sizing capital = `portfolio_equity * 0.02`.
     - For stock trade: `max_qty = int(sizing_capital / price)`. If proposed quantity > `max_qty`, scale down the quantity in `target_legs` to `max_qty`. If `max_qty <= 0`, reject the trade (`is_approved = False`).
     - For vertical spread trade (consists of one short leg and one long leg): `width = abs(short_leg["strike"] - long_leg["strike"])`, `net_credit = short_leg["price"] - long_leg["price"]`. The risk is `(width - net_credit) * 100` per contract. `max_contracts = int(sizing_capital / ((width - net_credit) * 100))`. If absolute proposed quantity > `max_contracts`, scale down both legs' quantities to `max_contracts` (preserving signs). If `max_contracts <= 0`, reject the trade (`is_approved = False`).
4. Total stock exposure limit (1.6x Rule):
   - Calculate the total simulated stock exposure (value of existing stock positions + value of proposed stock purchases).
   - Value of stock position = `quantity * current_price` (or `quantity * price` for proposed).
   - If total stock exposure > `1.6 * portfolio_equity` (exactly greater than 1.6x, e.g. 1.601x is blocked, but exactly 1.6x is allowed), reject the trade (`is_approved = False`).
5. Cancel Stale Orders:
   - Check `open_orders` list in the state.
   - For any order with `age_seconds > 125` (exactly greater than 125s), cancel it.
   - Add its `order_id` to the `cancelled_orders` list, and remove it from `open_orders` or update it.
6. Preserves existing portfolio greeks and margin calculations or custom overrides in `risk_manager_node`.

Verify your changes by running pytest:
```powershell
set GOOGLE_API_KEY=mock
venv\Scripts\python.exe -m pytest tests/test_tier1_feature_coverage.py -k "risk_manager"
venv\Scripts\python.exe -m pytest tests/test_tier2_boundary_corner.py -k "risk_manager"
```
Ensure all 10 risk manager tests pass.
Document your implementation, changes, and verification commands/results in `.agents/worker_m4/handoff.md`.
