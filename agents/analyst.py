from core.state import AgentState
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
import json

# Initialize the LLM
llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash")

def analyst_node(state: AgentState) -> dict:
    ticker = state.get("ticker", "SPY")
    price = state.get("price", 420.0)
    option_chain = state.get("option_chain", {}) or {}
    critique = state.get("evaluation_critique")
    
    # 1. Instruct the LLM to analyze the stock and select an appropriate strategy (Stock vs. Options spread)
    system_prompt = (
        "You are an expert derivatives analyst. Analyze the market for the given ticker and choose one of these strategies:\n"
        "1. 'BULL_PUT_SPREAD' (Moderately bullish/income strategy: sell a put below the price, buy a put further OTM for protection)\n"
        "2. 'LONG_STOCK' (Bullish: buy the stock directly)\n"
        "3. 'HOLD' (Neutral: no new positions)\n\n"
        "You must respond ONLY with a JSON object in the following format (no other text):\n"
        "{\n"
        '  "signal": "BUY" or "HOLD",\n'
        '  "strategy": "BULL_PUT_SPREAD" or "LONG_STOCK" or "HOLD",\n'
        '  "strike_offset_short": <float, e.g. 5.0 for $5 below current price>,\n'
        '  "strike_offset_long": <float, e.g. 10.0 for $10 below current price>,\n'
        '  "reason": "<analysis rationale>"\n'
        "}"
    )
    
    prompt = f"Current stock price of {ticker} is ${price:.2f}. Suggest a trade decision."
    
    # Ingest critique if present from a previous run
    if critique:
        prompt += (
            f"\n\nCRITICAL STRATEGY CONSTRAINT (PREVIOUS CRITIQUE):\n{critique}\n\n"
            "Ingest the critique above, treat it as a hard constraint, and correct your trading signal to match our strategy parameters (e.g. do not recommend BUY if it violates the 200-day moving average rule)."
        )
    
    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt)
        ])
        
        # Extract the string content safely from the AIMessage object
        content = response.content if hasattr(response, 'content') else str(response)
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    parts.append(part["text"])
                else:
                    parts.append(str(part))
            content = " ".join(parts)
        else:
            content = str(content)
            
        # Clean potential JSON markdown blocks
        clean_content = content.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_content)
        
        signal = data.get("signal", "HOLD")
        strategy = data.get("strategy", "HOLD")
        reason = data.get("reason", "Neutral outlook.")
        offset_short = float(data.get("strike_offset_short") or 5.0)
        offset_long = float(data.get("strike_offset_long") or 10.0)
    except Exception as e:
        print(f"Error calling analyst LLM or parsing JSON: {e}. Defaulting to BULL_PUT_SPREAD.")
        signal = "BUY"
        strategy = "BULL_PUT_SPREAD"
        reason = f"Fallback: Bull Put Spread proposed. Error: {str(e)}"
        offset_short = 5.0
        offset_long = 10.0
        content = str(e)
        
    target_legs = None
    
    if signal == "BUY" and strategy == "BULL_PUT_SPREAD":
        target_short_strike = round((price - offset_short) / 5.0) * 5.0
        target_long_strike = round((price - offset_long) / 5.0) * 5.0
        
        # Expiration date: find the first available in the option chain
        expirations = sorted(list(set(opt["expiration_date"] for opt in option_chain.values())))
        exp_date = expirations[0] if expirations else "2026-07-17"
        
        short_sym = f"{ticker}{exp_date.replace('-','')[2:]}P{str(int(target_short_strike*1000)).zfill(8)}"
        long_sym = f"{ticker}{exp_date.replace('-','')[2:]}P{str(int(target_long_strike*1000)).zfill(8)}"
        
        short_contract = option_chain.get(short_sym)
        long_contract = option_chain.get(long_sym)
        
        # Fallback options generator if not found in chain
        if not short_contract:
            short_contract = {"contract_symbol": short_sym, "price": 3.0, "greeks": {"delta": -0.30, "gamma": 0.02, "theta": -0.08, "vega": 0.35, "iv": 0.20}}
        if not long_contract:
            long_contract = {"contract_symbol": long_sym, "price": 1.5, "greeks": {"delta": -0.15, "gamma": 0.01, "theta": -0.04, "vega": 0.20, "iv": 0.21}}
            
        target_legs = [
            {
                "symbol": short_sym,
                "underlying_symbol": ticker,
                "type": "put",
                "strike": target_short_strike,
                "expiration_date": exp_date,
                "quantity": -2, # Short 2 puts
                "price": short_contract["price"],
                "greeks": short_contract["greeks"]
            },
            {
                "symbol": long_sym,
                "underlying_symbol": ticker,
                "type": "put",
                "strike": target_long_strike,
                "expiration_date": exp_date,
                "quantity": 2, # Long 2 puts (defined risk)
                "price": long_contract["price"],
                "greeks": long_contract["greeks"]
            }
        ]
        print(f"Analyst proposed BULL_PUT_SPREAD: Short Put {short_sym} (at {target_short_strike}), Long Put {long_sym} (at {target_long_strike})")

    elif signal == "BUY" and strategy == "LONG_STOCK":
        target_legs = [
            {
                "symbol": ticker,
                "underlying_symbol": ticker,
                "type": "stock",
                "strike": None,
                "expiration_date": None,
                "quantity": 100, # Buy 100 shares
                "price": price,
                "greeks": {"delta": 1.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "iv": 0.0}
            }
        ]
        print(f"Analyst proposed LONG_STOCK: Buy 100 shares of {ticker} at {price}")

    # Return updates including the recommendations history for the evaluator
    new_rec = {
        "signal": signal,
        "strategy": strategy,
        "reason": reason,
        "price": price,
        "target_legs": target_legs
    }
    recs = (state.get("analysis_recs") or []) + [new_rec]

    return {
        "signal": signal,
        "risk_reason": f"Strategy: {strategy}. Rationale: {reason}",
        "target_legs": target_legs,
        "analysis_recs": recs,
        "evaluation_critique": "" # Clear the critique field
    }
