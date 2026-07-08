from typing import TypedDict, List, Optional, Dict, Any
from pydantic import BaseModel

# This is your "Whiteboard" - the memory for your agent
class AgentState(TypedDict):
    ticker: str
    signal: Optional[str]  # e.g., "BUY" or "SELL"
    is_approved: bool
    risk_reason: Optional[str]
    price: float
    user_approved: bool
    status: Optional[str]
    execution_log: Optional[str]
    quantity: int
    market_data: Dict[str, Any]
    analysis_recs: List[Dict[str, Any]]
    # New Reflector Fields
    evaluation_critique: str
    confidence_score: float  # Scale of 0.0 to 1.0
    risk_approved: bool
    
    # Sprint 4: Derivatives and Position Tracking
    portfolio_inventory: List[Dict[str, Any]]  # List of current positions (stock or options)
    margin_utilization: float                  # Current margin in use (USD)
    portfolio_equity: float                    # Net asset value of the portfolio (USD)
    cash: float                                # Available cash balance (USD)
    portfolio_greeks: Dict[str, float]         # Combined delta, theta, gamma
    option_chain: Dict[str, Any]               # Option chain data
    target_legs: Optional[List[Dict[str, Any]]] # Proposed options legs to trade

