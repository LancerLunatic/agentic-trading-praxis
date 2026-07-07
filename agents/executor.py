from core.state import AgentState
# import alpaca_trade_api as tradeapi # Uncomment when ready to connect

def execute_trade_node(state: AgentState) -> AgentState:
    print(f"--- EXECUTING TRADE: {state.get('ticker')} ---")
    
    ticker = state.get("ticker")
    quantity = state.get("quantity", 1)
    
    try:
        # PLACEHOLDER: This is where your actual Alpaca API call goes
        # api = tradeapi.REST(KEY, SECRET, BASE_URL)
        # api.submit_order(symbol=ticker, qty=quantity, side='buy', type='market', time_in_force='gtc')
        
        print(f"--- SUCCESS: Order for {quantity} shares of {ticker} placed. ---")
        
        return {
            "status": "COMPLETED",
            "execution_log": f"Successfully bought {quantity} of {ticker}."
        }
        
    except Exception as e:
        print(f"--- ERROR in executor: {e} ---")
        return {
            "status": "FAILED",
            "execution_log": f"Trade failed: {str(e)}"
        }