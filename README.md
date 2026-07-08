# Enterprise Agentic Trading System (Praxis)

A production-grade, multi-agent quantitative finance and risk management framework built on **LangGraph**. The system orchestrates complex market analysis, structured derivatives pricing, portfolio-wide risk validation, and human-in-the-loop governance.

---

## 30-Second System Architecture

The core of the system is the **Reflector Loop**, which continuously refines trading decisions through iterative critique before running safety checks and executing trades.

```
                  [START]
                     │
                     ▼
             ┌───────────────┐
             │ Data Provider │◄─────────────────────────────────┐
             │     Node      │                                  │
             └───────┬───────┘                                  │
                     │ (Asset Price & Option Chain)             │
                     ▼                                          │
             ┌───────────────┐                                  │
             │ Analyst Node  │◄────────────┐                    │
             │    (LLM)      │             │                    │
             └───────┬───────┘             │                    │
                     │ (Target Legs)       │                    │
                     ▼                     │ (Low Confidence    │
             ┌───────────────┐             │  Critique Retry)   │ (Resume /
             │   Evaluator   ├─────────────┘                    │  Override)
             │  (Guardrail)  │                                  │
             └───────┬───────┘                                  │
                     │ (Confidence >= 70%)                      │
                     ▼                                          │
             ┌───────────────┐                                  │
             │ Risk Manager  ├──────────────────────────────────┘
             │  (Greeks/OTM) │ (Breach: Interrupt for Human Approval)
             └───────┬───────┘
                     │ (Approved)
                     ▼
             ┌───────────────┐
             │ Executor Node │
             └───────┬───────┘
                     │
                     ▼
                   [END]
```

---

## Technical Engineering Achievements

This framework prioritizes software robustness, safety boundaries, and resource efficiency over simple algorithmic execution.

### 🛡️ Strict Pydantic Validation Guardrails
All trading signals, evaluation critiques, and execution logs enforce rigid schemas via Pydantic models. This ensures absolute runtime reliability and prevents formatting drifts from LLM outputs.

### 💾 Postgres-Backed State Checkpointing
Leverages LangGraph's persistent state saver to enable transactionally safe checkpoints. The system supports full state rollback, session tracing, and persistent resume states for Human-in-the-Loop workflows.

### 📐 Mathematical Option Pricing Fallback
To mitigate API rate limits or lack of premium market data subscriptions, the system implements a self-contained, mathematically rigorous **Black-Scholes Options Pricing Engine**. It computes Option Prices, Delta ($\Delta$), Gamma ($\Gamma$), Theta ($\Theta$), and Vega ($\mathcal{V}$) dynamically using native Python optimization.

### 📊 Multi-Leg Derivatives & Margin Management
Tracks complex inventory structures (e.g. short vertical spreads, covered calls, iron butterflies) rather than simple stock holdings. The Risk Manager dynamically evaluates:
*   **Portfolio Delta Limit:** Rejects or holds trades if aggregate portfolio delta exceeds $\pm 1000$ shares equivalent.
*   **Premium Threshold:** Enforces that vertical credit spreads collect at least $30\%$ of the spread width.
*   **Margin Utilization Ceiling:** Calculates margin requirements for defined/undefined risk positions; interrupts if margin exceeds $80\%$ of portfolio equity.

### 📉 Cost-Conscious Telemetry & Token Sampling
Features an adaptive telemetry and logging layer with built-in sampling limits and token compression. The framework ensures maximum observability while maintaining low token footprint, preventing rate limits on free-tier LLM endpoints.

---

## Getting Started

### 1. Environment Setup
Create a `.env` file in the root directory:
```bash
GEMINI_API_KEY=your_gemini_api_key
ALPACA_API_KEY=your_alpaca_key (optional, defaults to mock simulator)
ALPACA_SECRET_KEY=your_alpaca_secret
```

### 2. Run the Backtest Simulation
To run the full multi-agent simulation loop and output historical performance reports:
```bash
python simulation.py
```