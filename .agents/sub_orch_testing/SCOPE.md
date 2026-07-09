# Scope: E2E Testing Track

## Architecture
- The E2E test suite treats the compiled LangGraph workflow (`app` in `main.py`) and/or `simulation.py` as an opaque box.
- It provides a mock environment for Alpaca API and Gemini LLM.
- It tests features through graph invocation and output state verification.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Test Infra & Mocks | Create mock wrappers for Alpaca API and LLM, set up pytest runner | None | DONE |
| 2 | Tier 1 Tests | Implement >=20 Feature Coverage tests (>=5 per feature) | M1 | DONE |
| 3 | Tier 2 Tests | Implement >=20 Boundary & Corner Case tests (>=5 per feature) | M1 | DONE |
| 4 | Tier 3 Tests | Implement >=4 Cross-Feature Combination tests | M2, M3 | DONE |
| 5 | Tier 4 Tests | Implement >=5 Real-World Application Scenarios | M2, M3, M4 | DONE |
| 6 | Verification & Publication | Run E2E test suite (verify failures on legacy code), write TEST_READY.md | M2, M3, M4, M5 | DONE |

## Interface Contracts
- E2E tests import `app` from `main.py` or run `simulation.py` via subprocess/direct call.
- Mocks intercept `alpaca_trade_api.REST` and `ChatGoogleGenerativeAI`.
