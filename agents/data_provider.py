from core.state import AgentState
import alpaca_trade_api as tradeapi
import os

def data_provider_node(state: AgentState) -> AgentState:
    ticker = state.get("ticker") # Pull tickers from langgraph UI
    
    if not ticker:
        raise ValueError("No ticker provided in the graph input state!")
        
    print(f"--- FETCHING DATA FOR: {ticker} ---")

    try:
        print(f"DEBUG KEYS: Key ID exists: {bool(os.environ.get('ALPACA_API_KEY'))}")
        
        # Initialize the Alpaca API client using environment variables
        api = tradeapi.REST(
            key_id=os.environ.get("ALPACA_API_KEY"),
            secret_key=os.environ.get("ALPACA_SECRET_KEY"),
            base_url="https://paper-api.alpaca.markets" # Hardcoded to paper trading for safety
        )
        
        # Fetch the latest trade data to get a real, dynamic price
        latest_trade = api.get_latest_trade(ticker.upper())
        actual_price = float(latest_trade.price)
        
        print(f"--- SUCCESS: {ticker} price is ${actual_price:.2f} ---")
        
        # Return the actual price back to the graph state
        return {"price": actual_price, "ticker": ticker}
        
    except Exception as e:
        import traceback
        print(f"--- ERROR in data_provider: {e} ---")
        traceback.print_exc()  # <--- Add this to see the hidden error
        return {"price": 0.0, "ticker": ticker}