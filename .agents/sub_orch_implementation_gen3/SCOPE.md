# Scope: Implementation Track (Remediation Gen3)

## Architecture
- The system is a MemeStocksStrategy trading agent integrated into a LangGraph workflow.
- Key modules:
  - `core/state.py`: defines the schema shared across all nodes in the graph.
  - `agents/data_provider.py`: data provider node.
  - `agents/analyst.py`: screening & analyst node.
  - `agents/risk_manager.py`: risk and portfolio management node.
  - `agents/executor.py`: trade execution node.
  - `simulation.py`: backtesting engine.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | State Schema Extension | Update core/state.py with screening lists and portfolio variables | None | DONE |
| 2 | High-Velocity Ingestion | Batch-fetch market data, filter top 75, option chains, VIX, mock/sim fallback in agents/data_provider.py | M1 | DONE |
| 3 | Quant Screening & Sentiment | Implement VIX filter, IV velocity, Call/Put ratio, top 15 ranking, LLM proposal in agents/analyst.py | M2 | DONE |
| 4 | Risk Sizing & Portfolio Guardrails | Stop-loss (-15%), take-profit (+33%), drawdown breaker (-5%), 2% sizing, 1.6x exposure in agents/risk_manager.py | M3 | DONE |
| 5 | Execution, Slippage & Reporting | Submit orders, calculate slippage, format daily summary in agents/executor.py | M4 | DONE |
| 6 | E2E Integration and Simulation | Harmonize simulation.py with graph states, run simulation | M5 | DONE |
| 7 | Integrity Remediation | Fix R1, R2, R3, R4 violations reported by Forensic Auditor | M6 | DONE (verified) |

## Interface Contracts
- Shared State `AgentState` must include:
  - `vix_price`: float
  - `regime`: str ("BULL" or "BEAR")
  - `screened_candidates`: List[str]
  - `proposed_trades`: List[Dict[str, Any]]
  - `previous_iv`: Dict[str, float]
  - `start_of_day_equity`: float
  - `daily_slippage`: float
  - `liquidations`: List[Dict[str, Any]]
  - `portfolio_inventory`: List[Dict[str, Any]]
  - `cash`: float
  - `portfolio_equity`: float
