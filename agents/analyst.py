from core.state import AgentState
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

# Initialize the LLM
llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash")

def analyst_node(state: AgentState) -> dict:
    ticker = state.get("ticker")
    price = state.get("price")
    
    # 1. Ask the model for analysis
    prompt = f"Analyze the market for {ticker} currently at ${price}. Provide a clear BUY, SELL, or HOLD recommendation."
    response = llm.invoke([HumanMessage(content=prompt)])
    
    # 2. Extract the string content safely from the AIMessage object
    content = response.content if hasattr(response, 'content') else str(response)
    
    # 3. Simple string matching on the model's text response
    if "BUY" in content.upper():
        decision = "BUY"
    elif "SELL" in content.upper():
        decision = "SELL"
    else:
        decision = "HOLD"
    
    # 4. Return updates to the graph state
    return {
        "signal": decision, 
        "risk_reason": content
    }