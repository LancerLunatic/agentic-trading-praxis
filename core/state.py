from typing import TypedDict, List, Optional
from pydantic import BaseModel
from typing import TypedDict, List, Dict, Any

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
