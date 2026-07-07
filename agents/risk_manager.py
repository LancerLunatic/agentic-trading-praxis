from core.state import AgentState
from langgraph.types import interrupt
from typing import Dict, Any

def risk_manager_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validates trade parameters against risk parameters.
    Triggers a Human-in-the-Loop breakpoint if safety rules are breached.
    """
    price = state.get("price", 0)
    ticker = state.get("ticker", "UNKNOWN")
    quantity = state.get("quantity", 1)
    
    # Check if the asset price breaches our $500 parameter safety ceiling
    # Also verify that the human hasn't already explicitly approved this state path
    if price >= 500 and not state.get("user_approved"):
        
        # This clean call completely pauses the graph and bubbles up a custom payload to Studio
        human_decision = interrupt({
            "action": "MANUAL_APPROVAL_REQUIRED",
            "reason": f"Asset {ticker} trading value exceeds the $500 parameter limit (${price:.2f})",
            "total_notional": price * quantity
        })
        
        # Process the manual override feedback injected back via Command(resume=...)
        if human_decision == "approve":
            return {
                "user_approved": True, 
                "status": "Override granted by user. Proceeding to execution pipeline."
            }
        else:
            return {
                "user_approved": False, 
                "status": f"Order aborted for {ticker}: Overruled by human supervisor."
            }
            
    # Auto-pass the execution node if the price is safely under $500
    return {"user_approved": True, "status": "Automated risk check passed."}