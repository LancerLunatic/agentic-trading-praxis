from pydantic import BaseModel, Field
from core.state import AgentState
from typing import Dict, Any

class EvaluationSchema(BaseModel):
    critique: str = Field(description="Critique of the trading logic and assumptions.")
    confidence: float = Field(description="Confidence score from 0.0 (poor) to 1.0 (bulletproof).")

def evaluator_node(state: AgentState) -> Dict[str, Any]:
    # Extract trading metrics and signal from state
    price = state.get("price", 0.0)
    spy_200_sma = state.get("spy_200_sma", 0.0)
    signal = state.get("signal", "HOLD")
    reflection_count = state.get("reflection_count", 0)
    
    # 200-MA strategy guardrail: Buy and hold SPY only if price is strictly below 200-day SMA.
    # Therefore, if price is greater than or equal to spy_200_sma and signal is BUY, it is a violation.
    if price >= spy_200_sma and signal == "BUY":
        confidence = 0.5
        critique = (
            f"Strategy violation: Buy signal issued for SPY when its current price (${price:.2f}) "
            f"is greater than or equal to its 200-day SMA (${spy_200_sma:.2f})."
        )
    else:
        confidence = 0.85
        critique = "Critique passed: trade signal conforms to moving average technical guardrails."
        
    updates = {
        "evaluation_critique": critique,
        "confidence_score": confidence
    }
    
    # If confidence is low and we have not exceeded the reflection count limit of 3,
    # increment reflection_count by 1 to trigger the corrector loop.
    if confidence < 0.70 and reflection_count < 3:
        updates["reflection_count"] = reflection_count + 1
        
    return updates
