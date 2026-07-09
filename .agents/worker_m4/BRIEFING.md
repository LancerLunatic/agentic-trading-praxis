# BRIEFING — 2026-07-08T20:12:35Z

## Mission
Implement Milestone 4: Risk Sizing & Portfolio Guardrails in `agents/risk_manager.py`.

## 🔒 My Identity
- Archetype: implementer/qa
- Roles: implementer, qa, specialist
- Working directory: c:/Users/apoll/Documents/agentic-trading-praxis/.agents/worker_m4
- Original parent: 18cdffbe-5044-414c-b1c2-b9fc246c1c2d
- Milestone: Milestone 4: Risk Sizing & Portfolio Guardrails

## 🔒 Key Constraints
- CODE_ONLY network mode: no external requests.
- DO NOT CHEAT: all logic must be genuine, no hardcoding.
- Preserve existing portfolio greeks and margin calculations or custom overrides in `risk_manager_node`.

## Current Parent
- Conversation ID: 18cdffbe-5044-414c-b1c2-b9fc246c1c2d
- Updated: 2026-07-08T20:12:35Z

## Task Summary
- **What to build**: Stop-Loss/Take-Profit liquidation, intraday drawdown breaker, 2% capital rule trade sizing, 1.6x stock exposure limit, stale orders cancellation.
- **Success criteria**: All 10 risk manager tests pass.
- **Interface contracts**: `agents/risk_manager.py` and `tests/`
- **Code layout**: Python files in `agents/`, tests in `tests/`

## Key Decisions Made
- Executed SL/TP liquidations and intraday drawdown breaker before processing trade sizing rules and credit spread rules, ensuring that current holdings are monitored even if the signal is "HOLD".
- Preserved existing simulated margin and portfolio greeks computations.
- Ensured target legs were scaled down correctly and updated target legs were returned in state updates for execution.

## Change Tracker
- **Files modified**:
  - `agents/risk_manager.py`: Implemented position monitoring, drawdown breaker, 2% capital sizing, 1.6x exposure limit, stale order cancellation.
- **Build status**: Pass
- **Pending issues**: None.

## Quality Status
- **Build/test result**: All 10 risk manager tests pass (5 in tier 1, 5 in tier 2).
- **Lint status**: Clean.
- **Tests added/modified**: None (utilized and verified against 10 comprehensive project tests).

## Loaded Skills
- None.

## Artifact Index
- c:/Users/apoll/Documents/agentic-trading-praxis/.agents/worker_m4/ORIGINAL_REQUEST.md — Original Request
- c:/Users/apoll/Documents/agentic-trading-praxis/.agents/worker_m4/progress.md — Progress tracker
- c:/Users/apoll/Documents/agentic-trading-praxis/.agents/worker_m4/handoff.md — Final Handoff Report
