# Migration Plan: MemeStocksStrategy to LangGraph

## Objective
Migrate legacy QuantConnect trading script (MemeStocksStrategy) into an asynchronous, multi-agent trading framework using LangGraph.

## Strategy & Approach
We will follow the Project Pattern:
1. **Decomposition**: Define concrete milestones for high-velocity data ingestion, quantitative screening, risk/portfolio sizing, execution/reporting, and E2E testing.
2. **Dual-Track Execution**:
   - **E2E Testing Track**: Design and build a comprehensive test suite (Tiers 1-4) derived from user requirements to verify the migrated strategy.
   - **Implementation Track**: Migrate nodes and core logic module-by-module.
3. **Verification**: Run E2E test suite and pass all checks, followed by adversarial coverage hardening (Tier 5) and a Forensic Audit.

## Milestones
- **M1: Core Exploration & Architecture Mapping**: Analyze current codebase, model schemas, and state layout.
- **M2: Data Ingestion (R1)**: Implement data provider node (underlying selection, options chain snapshots, fallback simulation).
- **M3: Screening & Sentiment Node (R2)**: Implement quant/sentiment logic (VIX checks, ATM IV change, Call/Put ratios, ranking).
- **M4: Risk & Portfolio Node (R3)**: Implement risk limits (2% size, 1.6x exposure limit, unrealized PL liquidations, drawdown breaker, order cancel).
- **M5: Execution & Reporting Node (R4)**: Implement REST order routing, slippage computation, daily summary formatting.
- **M6: E2E Integration and Simulation**: Verify the entire system passes simulated backtesting using `simulation.py`.

## Verification Method
- programmatically execute simulated backtests over a 30-day historical window.
- Ensure 100% test pass on all requirements.
- Clean forensic audit.
