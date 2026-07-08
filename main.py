from dotenv import load_dotenv
# Refine Environment Handling: Explicitly loaded at the absolute entry point
load_dotenv()

from langgraph.graph import StateGraph, START, END
from core.state import AgentState
from agents.analyst import analyst_node
from agents.risk_manager import risk_manager_node
from agents.data_provider import data_provider_node
from agents.executor import execute_trade_node
from agents.evaluator import evaluator_node

# 1. Define the routing logic
def router(state: AgentState):
    # If the risk_manager approved it (or it didn't need approval), 
    # we proceed to the 'execution' node. If not, we end.
    if state.get("user_approved", False):
        return "execute_trade"
    return END

def evaluator_router(state: AgentState):
    # Route back to analyst if confidence is low, unless max retries exceeded
    confidence = state.get("confidence_score", 1.0)
    reflection_count = state.get("reflection_count", 0)
    
    if confidence < 0.7 and reflection_count < 3:
        return "retry"
    return "proceed"

# 2. Initialize the Graph
workflow = StateGraph(AgentState)

# 3. Add Nodes
workflow.add_node("data_provider", data_provider_node)
workflow.add_node("analyst", analyst_node)
workflow.add_node("risk_manager", risk_manager_node)
workflow.add_node("execute_trade", execute_trade_node)
workflow.add_node("evaluator", evaluator_node)

# 4. Define the Flow
workflow.add_edge(START, "data_provider")
workflow.add_edge("data_provider", "analyst")
workflow.add_edge("analyst", "evaluator")         # Feed analysis to evaluator

# Replace static edge from evaluator with a conditional edge for looping/retry
workflow.add_conditional_edges(
    "evaluator",
    evaluator_router,
    {
        "retry": "analyst",
        "proceed": "risk_manager"
    }
)

workflow.add_edge("risk_manager", END)

# Use add_conditional_edges to decide if we proceed to execution or exit
workflow.add_conditional_edges(
    "risk_manager",
    router,
    {
        "execute_trade": "execute_trade",
        END: END
    }
)

app = workflow.compile()

# Apply the custom telemetry patch to the compiled app for cost-conscious tracing
from core.telemetry import patch_app_with_telemetry
app = patch_app_with_telemetry(app)