## 2026-07-08T20:14:04Z

Refine `agents/risk_manager.py` to fix three specific risk manager logic vulnerabilities identified during the peer review:
1. Short Stock Position Sizing:
   In the 2% capital sizing rule check for stocks, use absolute values to check and scale down short stock positions:
   ```python
   if abs(leg["quantity"]) > max_qty:
       sign = 1 if leg["quantity"] > 0 else -1
       leg["quantity"] = sign * max_qty
   ```
2. Debit Spreads blocked by Credit Spread rule:
   Ensure the 30% credit spread premium ratio rule only applies to credit spreads (`net_credit > 0`). If it is a debit spread (`net_credit <= 0`), do not apply this constraint (meaning do not reject it for having a low/negative ratio).
3. Total Stock Exposure limit:
   Ensure the 1.6x exposure limit check uses gross exposure (absolute value of stock quantities) rather than net exposure:
   - Sum `abs(pos_qty) * pos_price` for existing inventory.
   - Sum `abs(leg_qty) * leg_price` for proposed trades.

Verify your changes by running pytest:
```powershell
set GOOGLE_API_KEY=mock
venv\Scripts\python.exe -m pytest tests/test_tier1_feature_coverage.py -k "risk_manager"
venv\Scripts\python.exe -m pytest tests/test_tier2_boundary_corner.py -k "risk_manager"
```
Confirm all tests continue to pass.
Document your changes in `.agents/worker_m4_fix/handoff.md`.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.
