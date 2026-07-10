from core.state import AgentState
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
import json

# Initialize the LLM
import os
if os.environ.get("GOOGLE_API_KEY") == "mock":
    from unittest.mock import MagicMock
    llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = (
        '{\n'
        '  "signal": "BUY",\n'
        '  "strategy": "BULL_PUT_SPREAD",\n'
        '  "strike_offset_short": 5.0,\n'
        '  "strike_offset_long": 10.0,\n'
        '  "reason": "Sufficient IV velocity and bullish option structure"\n'
        '}'
    )
    llm.invoke.return_value = mock_response
else:
    llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash")

def analyst_node(state: AgentState) -> dict:
    ticker = state.get("ticker", "SPY")
    price = state.get("price", 420.0)
    option_chain = state.get("option_chain", {}) or {}
    critique = state.get("evaluation_critique")
    
    # 1. VIX regime and defensive mode check
    vix_price = state.get("vix_price")
    regime = state.get("regime", "BULL")
    defensive_cash_mode = state.get("defensive_cash_mode", False)
    
    if (vix_price is not None and vix_price > 20.50) or regime == "BEAR" or defensive_cash_mode:
        return {
            "regime": "BEAR",
            "signal": "HOLD",
            "proposed_trades": [],
            "target_legs": [],
            "risk_reason": "BEAR regime, defensive cash mode, or VIX shock active. Trading halted.",
            "evaluation_critique": ""
        }
    
    # Helper function to find ATM option IV for a given symbol
    def get_atm_iv(sym, price_val):
        t_options = []
        for opt_sym, opt in option_chain.items():
            if opt.get("underlying_symbol") == sym:
                t_options.append(opt)
            elif opt_sym.startswith(sym) and len(opt_sym) >= len(sym) + 6 and opt_sym[len(sym):len(sym)+6].isdigit():
                t_options.append(opt)
        if not t_options:
            return None
        
        # Find option with strike closest to price_val
        # Default to the underlying price (or strike if not found) of the first option if price_val is None
        ref_price = price_val if price_val is not None else t_options[0].get("underlying_price", t_options[0].get("strike", 0.0))
        atm_opt = min(t_options, key=lambda x: abs(x.get("strike", 0.0) - ref_price))
        
        # Get IV
        if "greeks" in atm_opt and "iv" in atm_opt["greeks"]:
            return atm_opt["greeks"]["iv"]
        elif "iv" in atm_opt:
            return atm_opt["iv"]
        return None

    # 4. Candidate ranking
    screened_candidates = state.get("screened_candidates", []) or []
    previous_iv_dict = dict(state.get("previous_iv") or {})
    candidate_velocities = {}
    
    for cand in screened_candidates:
        cand_price = price if cand == ticker else None
        cand_current_iv = get_atm_iv(cand, cand_price)
        if cand_current_iv is not None:
            orig_prev_iv = state.get("previous_iv", {}).get(cand) if state.get("previous_iv") else None
            if orig_prev_iv is not None:
                velocity = cand_current_iv - orig_prev_iv
                if velocity > 0:
                    candidate_velocities[cand] = velocity
            previous_iv_dict[cand] = cand_current_iv

    ranked_candidates = sorted(candidate_velocities.keys(), key=lambda c: abs(candidate_velocities[c]), reverse=True)
    ranked_candidates = ranked_candidates[:15]

    # Initialize signal, strategy, reason
    signal = "BUY"
    strategy = "BULL_PUT_SPREAD"
    reason = "Bullish outlook."

    # 2. Call/Put volume ratio constraint
    call_put_ratio = state.get("call_put_ratio")
    if call_put_ratio is not None and call_put_ratio < 1.10:
        signal = "HOLD"
        strategy = "HOLD"
        reason = f"Call/Put ratio {call_put_ratio:.2f} is below 1.10 constraint."

    # 3. IV velocity screening for the primary ticker
    primary_current_iv = get_atm_iv(ticker, price)
    if primary_current_iv is not None:
        orig_prev_iv = state.get("previous_iv", {}).get(ticker) if state.get("previous_iv") else None
        if orig_prev_iv is not None:
            primary_velocity = primary_current_iv - orig_prev_iv
            if primary_velocity <= 0:
                signal = "HOLD"
                strategy = "HOLD"
                reason = f"IV velocity for {ticker} is stagnant or decreased ({primary_current_iv:.4f} <= {orig_prev_iv:.4f})."
        previous_iv_dict[ticker] = primary_current_iv

    target_legs = None

    if signal == "HOLD":
        new_rec = {
            "signal": signal,
            "strategy": strategy,
            "reason": reason,
            "price": price,
            "target_legs": None
        }
        recs = (state.get("analysis_recs") or []) + [new_rec]
        return {
            "signal": signal,
            "risk_reason": f"Strategy: {strategy}. Rationale: {reason}",
            "target_legs": None,
            "analysis_recs": recs,
            "evaluation_critique": "",
            "regime": regime,
            "ranked_candidates": ranked_candidates,
            "previous_iv": previous_iv_dict
        }

    # 5. LLM proposal: If signal is not "HOLD", invoke ChatGoogleGenerativeAI
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
        
    if signal == "BUY" and strategy == "BULL_PUT_SPREAD":
        target_short_strike = round((price - offset_short) / 5.0) * 5.0
        target_long_strike = round((price - offset_long) / 5.0) * 5.0
        
        expirations = sorted(list(set(opt["expiration_date"] for opt in option_chain.values() if "expiration_date" in opt)))
        exp_date = expirations[0] if expirations else "2026-07-17"
        
        short_sym = f"{ticker}{exp_date.replace('-','')[2:]}P{str(int(target_short_strike*1000)).zfill(8)}"
        long_sym = f"{ticker}{exp_date.replace('-','')[2:]}P{str(int(target_long_strike*1000)).zfill(8)}"
        
        short_contract = option_chain.get(short_sym)
        long_contract = option_chain.get(long_sym)
        
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
                "quantity": -2,
                "price": short_contract.get("price", 3.0),
                "greeks": short_contract.get("greeks", {"delta": -0.30, "gamma": 0.02, "theta": -0.08, "vega": 0.35, "iv": 0.20})
            },
            {
                "symbol": long_sym,
                "underlying_symbol": ticker,
                "type": "put",
                "strike": target_long_strike,
                "expiration_date": exp_date,
                "quantity": 2,
                "price": long_contract.get("price", 1.5),
                "greeks": long_contract.get("greeks", {"delta": -0.15, "gamma": 0.01, "theta": -0.04, "vega": 0.20, "iv": 0.21})
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
                "quantity": 100,
                "price": price,
                "greeks": {"delta": 1.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "iv": 0.0}
            }
        ]
        print(f"Analyst proposed LONG_STOCK: Buy 100 shares of {ticker} at {price}")

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
        "evaluation_critique": "",
        "regime": regime,
        "ranked_candidates": ranked_candidates,
        "previous_iv": previous_iv_dict
    }
