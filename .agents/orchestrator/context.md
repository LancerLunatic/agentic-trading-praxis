# Context Summary

## Project Context
The goal is to migrate `MemeStocksStrategy` to a LangGraph multi-agent framework. Currently, there is a simple LangGraph structure in `main.py` with placeholder/basic nodes (`data_provider`, `analyst`, `evaluator`, `risk_manager`, `execute_trade`). We need to implement complex, high-velocity data ingestion, quantitative screening, sentiment processing, and risk constraints.

## Current State
- `plan.md`, `progress.md`, `BRIEFING.md` have been initialized.
- Heartbeat cron timer is running.
- Initial files examined: `main.py`, `simulation.py`, `core/state.py`, `agents/*.py`.
- No subagents have been spawned yet.
