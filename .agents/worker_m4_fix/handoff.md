# Handoff Report - Risk Manager Vulnerability Fixes

## 1. Observation
- **Short Stock Position Sizing check**: In `agents/risk_manager.py`, the existing implementation of the 2% capital sizing rule check for stocks compared the signed `leg["quantity"]` to `max_qty` (line 250):
  ```python
  if leg["quantity"] > max_qty:
      leg["quantity"] = max_qty
  ```
  This allowed short positions (negative quantity) to bypass the scaling logic entirely because a negative number is always less than `max_qty`.
- **Credit Spread Premium Ratio check**: In `agents/risk_manager.py` (lines 191-209), the 30% credit spread premium ratio constraint was applied to all vertical spreads where `is_credit_spread = True`. However, debit vertical spreads have a negative `net_credit`, resulting in a negative `premium_ratio` (e.g., `-0.40`), which triggers an automatic rejection because it is less than `0.30`.
- **Total Stock Exposure limit check**: In `agents/risk_manager.py` (lines 292-303), the total stock exposure limit (1.6x) was calculated by summing the signed quantities of stocks, netting out long and short positions:
  ```python
  total_stock_exposure += pos_qty * pos_price
  ...
  total_stock_exposure += leg_qty * leg_price
  ```
  This allowed a portfolio with high gross stock exposure (but low net stock exposure due to offsetting long/short stock positions) to bypass the 1.6x exposure limit check.

- **Test execution commands and outputs**:
  - Command: `$env:GOOGLE_API_KEY="mock"; venv\Scripts\python.exe -m pytest tests/test_tier1_feature_coverage.py -k "risk_manager"`
    Result: `5 passed, 15 deselected, 1 warning in 3.62s`
  - Command: `$env:GOOGLE_API_KEY="mock"; venv\Scripts\python.exe -m pytest tests/test_tier2_boundary_corner.py -k "risk_manager"`
    Result: `8 passed, 15 deselected, 1 warning in 3.79s` (including the 3 new tests added).

## 2. Logic Chain
- **Short Stock Position Sizing**: By replacing the check with `if abs(leg["quantity"]) > max_qty:`, both long and short stock positions are verified against the maximum allowed quantity. Scaling down short positions is correctly performed by preserving the short sign using `sign = 1 if leg["quantity"] > 0 else -1` and setting `leg["quantity"] = sign * max_qty`.
- **Debit Spread Exemption**: Wrapping the credit spread check with `if net_credit > 0:` ensures that the 30% credit spread premium ratio check is only applied to credit spreads. Debit spreads (where `net_credit <= 0`) are exempt from this threshold and are not rejected.
- **Gross Stock Exposure**: By modifying the calculation to use `abs(pos_qty)` and `abs(leg_qty)` instead of raw signed quantities, the exposure check accurately sums gross stock exposure across both long and short positions in the inventory and the proposed trade legs.
- **Validation**: Running the target risk manager unit tests verifies that all existing and new test coverage pass cleanly, indicating no functional regressions.

## 3. Caveats
- No caveats. The fixes address the peer review concerns directly using minimal changes and include dedicated unit tests for verification.

## 4. Conclusion
The three peer review findings in `agents/risk_manager.py` have been resolved. The risk manager now correctly checks and scales down short stock positions, exempts debit spreads from credit spread premium ratio requirements, and checks gross stock exposure under the 1.6x limit.

## 5. Verification Method
Verify the fixes by executing the following commands in the workspace root directory:
```powershell
$env:GOOGLE_API_KEY="mock"
venv\Scripts\python.exe -m pytest tests/test_tier1_feature_coverage.py -k "risk_manager"
venv\Scripts\python.exe -m pytest tests/test_tier2_boundary_corner.py -k "risk_manager"
```
Ensure all 13 risk manager tests pass.
Inspect the newly added tests at the end of `tests/test_tier2_boundary_corner.py`:
- `test_risk_manager_short_stock_position_sizing`
- `test_risk_manager_debit_spread_not_blocked`
- `test_risk_manager_gross_stock_exposure_limit`
