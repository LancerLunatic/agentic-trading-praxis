# Original User Request

## Initial Request — 2026-07-09T06:51:48-04:00

You are the Implementation Sub-Orchestrator. Your working directory is c:/Users/apoll/Documents/agentic-trading-praxis/.agents/sub_orch_implementation_gen2.

Objectives:
1. Resume the Implementation Track for migrating the legacy QuantConnect MemeStocksStrategy to LangGraph.
2. Read the previous implementation sub-orchestrator's directory at c:/Users/apoll/Documents/agentic-trading-praxis/.agents/sub_orch_implementation to recover context, including its BRIEFING.md, progress.md, and SCOPE.md.
3. The previous execution was interrupted by a server restart. No local Python source edits exist yet.
4. You must remediate the 4 integrity violations reported by the Forensic Auditor in c:/Users/apoll/Documents/agentic-trading-praxis/.agents/forensic_auditor/handoff.md:
   - R1 Ingestion: Filter top 75 candidates dynamically using price bounds and dollar volume metrics instead of using a hardcoded list of 8 large-cap tech tickers (applies to both Alpaca API and mock/simulation fallback).
   - R2 Ingestion/Screening: Fetch/generate options chain data for all screened candidates (not just the primary ticker) so the analyst's screening, ATM IV velocity calculation, and ranking logic operate dynamically on the candidate pool.
   - R3 Facade Assets: Remove the pre-populated stock/option positions from the data provider node. The backtest simulation must start with an empty portfolio inventory and properly track cash transactions.
   - R4 Router/Liquidations: Correct the graph router in main.py and executor logic so stop-loss, take-profit, and drawdown liquidations are executed even when user_approved is False. Ensure proceeds from liquidations are added back to the cash balance.
5. Spawn a worker (teamwork_preview_worker) to implement these changes. Verify code changes by running the E2E test suite (venv\Scripts\python tests/run_tests.py) and simulation (venv\Scripts\python simulation.py).
6. Spawn independent reviewers (teamwork_preview_reviewer) and challengers (teamwork_preview_challenger) to verify correctness and robustness.
7. Run the Forensic Auditor (teamwork_preview_auditor) to perform integrity verification. The audit verdict must be CLEAN.
8. Update c:/Users/apoll/Documents/agentic-trading-praxis/PROJECT.md and your SCOPE.md status columns as work progresses.
9. Report back to the Project Orchestrator (parent conversation ID: d558578d-b875-4264-8b8b-789a61fd42a8) with your handoff.md when all implementation milestones are completed and verified.
