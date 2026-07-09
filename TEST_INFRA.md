# E2E Test Infra: MemeStocksStrategy Migration

## Test Philosophy
- Opaque-box, requirement-driven. We test the compiled LangGraph workflow as an integrated unit, mocking external service APIs (Alpaca, Google Gemini) to control inputs and check outputs/state transitions.
- Methodology: Category-Partition, Boundary Value Analysis, Pairwise Combinatorial Testing, and Real-World Workload Testing.

## Feature Inventory
| # | Feature | Source (Requirement) | Tier 1 | Tier 2 | Tier 3 |
|---|---------|---------------------|:------:|:------:|:------:|
| 1 | Data Ingestion & Fallback | PROJECT.md §1: Data Ingestion Node | 5 | 5 | ✓ |
| 2 | Quantitative Screening & Analyst | PROJECT.md §2: Screening & Analyst Node | 5 | 5 | ✓ |
| 3 | Risk & Portfolio Guardrails | PROJECT.md §3: Risk Manager Node | 5 | 5 | ✓ |
| 4 | Execution, Slippage & Reporting | PROJECT.md §4: Executor Node | 5 | 5 | ✓ |

## Test Architecture
- **Test Runner**: Pytest based (`pytest tests/`) or via `run_tests.py` script.
- **Mocks**: Mocks for `alpaca_trade_api.REST` and `ChatGoogleGenerativeAI` to simulate different market environments (VIX levels, option pricing, order books) and LLM choices.
- **Directory Layout**:
  - `tests/conftest.py` - Pytest fixtures and mocks configuration.
  - `tests/test_tier1_feature_coverage.py` - Happy path feature coverage.
  - `tests/test_tier2_boundary_corner.py` - Edge cases and boundaries.
  - `tests/test_tier3_cross_feature.py` - Pairwise feature interaction tests.
  - `tests/test_tier4_real_world.py` - Real-world workload and backtest simulation scenarios.
  - `tests/run_tests.py` - Test runner script.

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | Standard Bull Market Uptrend | Ingestion, Screening, Sizing, Execution, Reporting | Medium |
| 2 | High Volatility VIX Bear Halt | VIX Ingestion, Analyst Halt, Risk Management, Reporting | High |
| 3 | Sudden Market Crash & Stop-Loss | Ingestion, Sizing, Stop-Loss Liquidation, Execution | High |
| 4 | Emergency Daily Drawdown Breaker | Ingestion, Drawdown Breaker Liquidation, Regime shift | High |
| 5 | Position Over-exposure and Sizing | Risk sizing (2%), Exposure limit (1.6x), Execution | Medium |

## Coverage Thresholds
- Tier 1: >= 5 per feature (Total >= 20)
- Tier 2: >= 5 per feature (Total >= 20)
- Tier 3: >= 4 combination tests
- Tier 4: >= 5 realistic application scenarios
- Total E2E Tests: >= 49 tests
