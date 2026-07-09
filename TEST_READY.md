# E2E Test Suite Ready

## Test Runner
- Command: `venv\Scripts\python tests/run_tests.py`
- Expected: all tests pass with exit code 0 (once migration is fully implemented; on the legacy codebase 17 pass and 32 fail as expected).

## Coverage Summary
| Tier | Count | Description |
|------|------:|-------------|
| 1. Feature Coverage | 20 | 5 test cases per feature covering happy paths |
| 2. Boundary & Corner | 20 | 5 test cases per feature covering boundaries and edge cases |
| 3. Cross-Feature | 4 | Pairwise combination tests for features |
| 4. Real-World Application | 5 | Multi-day simulation scenario workloads |
| **Total** | **49** | |

## Feature Checklist
| Feature | Tier 1 | Tier 2 | Tier 3 | Tier 4 |
|---------|:------:|:------:|:------:|:------:|
| Data Ingestion & Fallback | 5 | 5 | ✓ | ✓ |
| Quantitative Screening & Analyst | 5 | 5 | ✓ | ✓ |
| Risk & Portfolio Guardrails | 5 | 5 | ✓ | ✓ |
| Execution, Slippage & Reporting | 5 | 5 | ✓ | ✓ |
