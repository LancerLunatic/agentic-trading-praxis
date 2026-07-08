from core.state import AgentState
import alpaca_trade_api as tradeapi
import os
import math
import requests
import re
from typing import Dict, Any, List

def normal_cdf(x: float) -> float:
    """Cumulative distribution function for standard normal distribution."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def normal_pdf(x: float) -> float:
    """Probability density function for standard normal distribution."""
    return math.exp(-0.5 * x**2) / math.sqrt(2.0 * math.pi)

def black_scholes_greeks(S: float, K: float, T: float, r: float, sigma: float, option_type: str):
    """
    Computes Black-Scholes option price and Greeks (Delta, Gamma, Theta, Vega).
    T is time to expiration in years.
    """
    if T <= 0.001:
        # Near expiration or expired
        if option_type.lower() == "call":
            price = max(0.0, S - K)
            delta = 1.0 if S > K else 0.0
            theta = 0.0
        else:
            price = max(0.0, K - S)
            delta = -1.0 if S < K else 0.0
            theta = 0.0
        gamma = 0.0
        vega = 0.0
        return price, delta, gamma, theta, vega

    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    if option_type.lower() == "call":
        price = S * normal_cdf(d1) - K * math.exp(-r * T) * normal_cdf(d2)
        delta = normal_cdf(d1)
        # Annual Theta
        theta = -(S * normal_pdf(d1) * sigma) / (2.0 * math.sqrt(T)) - r * K * math.exp(-r * T) * normal_cdf(d2)
    else:  # put
        price = K * math.exp(-r * T) * normal_cdf(-d2) - S * normal_cdf(-d1)
        delta = normal_cdf(d1) - 1.0
        # Annual Theta
        theta = -(S * normal_pdf(d1) * sigma) / (2.0 * math.sqrt(T)) + r * K * math.exp(-r * T) * normal_cdf(-d2)

    gamma = normal_pdf(d1) / (S * sigma * math.sqrt(T))
    vega = S * math.sqrt(T) * normal_pdf(d1)

    # Daily Theta
    theta_daily = theta / 365.0

    return price, delta, gamma, theta_daily, vega

def data_provider_node(state: AgentState) -> AgentState:
    ticker = state.get("ticker")
    timestamp = state.get("timestamp")
    
    if not ticker:
        raise ValueError("No ticker provided in the graph input state!")
        
    # Robust unpacking if ticker is passed as a list from LangGraph console
    if isinstance(ticker, list):
        if len(ticker) > 0:
            ticker = ticker[0]
        else:
            raise ValueError("Ticker list is empty!")
            
    if ticker:
        ticker = str(ticker).strip().upper()

    print(f"--- FETCHING DATA FOR: {ticker} (timestamp: {timestamp}) ---")

    # 1. Fetch current price of the underlying ticker
    actual_price = 0.0
    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    
    use_mock_data = False
    if not api_key or not secret_key or "your_alpaca" in api_key or "your_alpaca" in secret_key:
        use_mock_data = True
    
    if not use_mock_data:
        try:
            api = tradeapi.REST(
                key_id=api_key,
                secret_key=secret_key,
                base_url="https://paper-api.alpaca.markets"
            )
            from alpaca_trade_api.rest import TimeFrame
            if timestamp:
                # Backtesting mode: Fetch historical bars ending on timestamp
                ticker_bars = api.get_bars(ticker, TimeFrame.Day, end=timestamp, limit=1).df
                if not ticker_bars.empty:
                    actual_price = float(ticker_bars['close'].iloc[-1])
                else:
                    actual_price = 0.0
            else:
                # Live mode: Fetch the latest trade data
                latest_trade = api.get_latest_trade(ticker)
                actual_price = float(latest_trade.price)
        except Exception as e:
            print(f"Alpaca REST price check failed: {e}. Falling back to mock price.")
            use_mock_data = True
            
    if use_mock_data:
        # Default price for testing
        actual_price = 420.0

    print(f"--- SUCCESS: {ticker} price is ${actual_price:.2f} ---")

    # 2. Fetch/Compute SPY 200-day Simple Moving Average (SMA) (from Sprint 3)
    spy_200_sma = 0.0
    if not use_mock_data:
        try:
            from alpaca_trade_api.rest import TimeFrame
            if timestamp:
                spy_bars = api.get_bars("SPY", TimeFrame.Day, end=timestamp, limit=200).df
            else:
                spy_bars = api.get_bars("SPY", TimeFrame.Day, limit=200).df
                
            if not spy_bars.empty:
                spy_200_sma = float(spy_bars['close'].mean())
            else:
                spy_200_sma = 0.0
        except Exception as e:
            print(f"Alpaca SPY SMA fetch failed: {e}.")
            
    if use_mock_data or spy_200_sma == 0.0:
        # Fallback default
        spy_200_sma = 405.0

    print(f"--- SUCCESS: SPY 200-day SMA is ${spy_200_sma:.2f} ---")

    # 3. Fetch/Generate Option Chain
    option_chain = {}
    
    if not use_mock_data:
        try:
            url = f"https://data.alpaca.markets/v1beta1/options/snapshots/{ticker}"
            headers = {
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": secret_key,
                "accept": "application/json"
            }
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                res_data = response.json()
                snapshots = res_data.get("snapshots", {})
                for contract_symbol, snap in snapshots.items():
                    match = re.match(r"^([A-Z]+)(\d{6})([CP])(\d{8})$", contract_symbol)
                    if match:
                        und, date_part, cp, strike_part = match.groups()
                        expiration = f"20{date_part[0:2]}-{date_part[2:4]}-{date_part[4:6]}"
                        option_type = "call" if cp == "C" else "put"
                        strike = float(strike_part) / 1000.0
                    else:
                        continue
                        
                    greeks_data = snap.get("greeks", {}) or {}
                    quote_data = snap.get("latestQuote", {}) or {}
                    trade_data = snap.get("latestTrade", {}) or {}
                    
                    price = float(trade_data.get("price") or quote_data.get("ask", 0.0) or 0.0)
                    
                    option_chain[contract_symbol] = {
                        "contract_symbol": contract_symbol,
                        "underlying_symbol": ticker,
                        "type": option_type,
                        "strike": strike,
                        "expiration_date": expiration,
                        "price": price,
                        "bid": float(quote_data.get("bid") or price * 0.98),
                        "ask": float(quote_data.get("ask") or price * 1.02),
                        "greeks": {
                            "delta": float(greeks_data.get("delta") or 0.0),
                            "gamma": float(greeks_data.get("gamma") or 0.0),
                            "theta": float(greeks_data.get("theta") or 0.0),
                            "vega": float(greeks_data.get("vega") or 0.0),
                            "iv": float(greeks_data.get("impliedVolatility") or 0.0)
                        }
                    }
        except Exception as e:
            print(f"Alpaca Options API check failed: {e}. Falling back to BS generator.")

    # If option_chain is empty, run the mathematical Black-Scholes generator
    if not option_chain:
        print("--- GENERATING BLACK-SCHOLES OPTION CHAIN ---")
        expirations = [("2026-07-17", 10/365), ("2026-08-07", 30/365)]
        strikes = [float(k) for k in range(int(actual_price - 20), int(actual_price + 25), 5)]
        
        for exp_date, T in expirations:
            for strike in strikes:
                dist_pct = (actual_price - strike) / actual_price
                iv = 0.20 + 0.15 * (dist_pct ** 2)
                r = 0.045
                
                # Call option
                c_price, c_delta, c_gamma, c_theta, c_vega = black_scholes_greeks(actual_price, strike, T, r, iv, "call")
                c_symbol = f"{ticker}{exp_date.replace('-','')[2:]}C{str(int(strike*1000)).zfill(8)}"
                option_chain[c_symbol] = {
                    "contract_symbol": c_symbol,
                    "underlying_symbol": ticker,
                    "type": "call",
                    "strike": strike,
                    "expiration_date": exp_date,
                    "price": round(c_price, 2),
                    "bid": round(c_price * 0.97, 2),
                    "ask": round(c_price * 1.03, 2),
                    "greeks": {
                        "delta": round(c_delta, 4),
                        "gamma": round(c_gamma, 4),
                        "theta": round(c_theta, 4),
                        "vega": round(c_vega, 4),
                        "iv": round(iv, 4)
                    }
                }
                
                # Put option
                p_price, p_delta, p_gamma, p_theta, p_vega = black_scholes_greeks(actual_price, strike, T, r, iv, "put")
                p_symbol = f"{ticker}{exp_date.replace('-','')[2:]}P{str(int(strike*1000)).zfill(8)}"
                option_chain[p_symbol] = {
                    "contract_symbol": p_symbol,
                    "underlying_symbol": ticker,
                    "type": "put",
                    "strike": strike,
                    "expiration_date": exp_date,
                    "price": round(p_price, 2),
                    "bid": round(p_price * 0.97, 2),
                    "ask": round(p_price * 1.03, 2),
                    "greeks": {
                        "delta": round(p_delta, 4),
                        "gamma": round(p_gamma, 4),
                        "theta": round(p_theta, 4),
                        "vega": round(p_vega, 4),
                        "iv": round(iv, 4)
                    }
                }
                
    # 4. Initialize state parameters & pre-populate complex inventory if empty
    cash = state.get("cash", 100000.0)
    portfolio_equity = state.get("portfolio_equity", 100000.0)
    margin_utilization = state.get("margin_utilization", 0.0)
    
    portfolio_inventory = state.get("portfolio_inventory")
    if not portfolio_inventory:
        print("--- INITIALIZING COMPLEX PORTFOLIO INVENTORY ---")
        exp_date = "2026-07-17"
        short_strike = actual_price - 5.0
        long_strike = actual_price - 10.0
        
        short_strike = round(short_strike / 5.0) * 5.0
        long_strike = round(long_strike / 5.0) * 5.0
        
        short_sym = f"{ticker}{exp_date.replace('-','')[2:]}P{str(int(short_strike*1000)).zfill(8)}"
        long_sym = f"{ticker}{exp_date.replace('-','')[2:]}P{str(int(long_strike*1000)).zfill(8)}"
        
        short_opt = option_chain.get(short_sym, {
            "price": 3.50, 
            "greeks": {"delta": -0.35, "gamma": 0.02, "theta": -0.10, "vega": 0.40, "iv": 0.22}
        })
        long_opt = option_chain.get(long_sym, {
            "price": 1.80, 
            "greeks": {"delta": -0.18, "gamma": 0.01, "theta": -0.05, "vega": 0.25, "iv": 0.23}
        })
        
        portfolio_inventory = [
            # Long Stock
            {
                "symbol": ticker,
                "underlying_symbol": ticker,
                "type": "stock",
                "strike": None,
                "expiration_date": None,
                "quantity": 100,
                "price": actual_price - 2.0,
                "current_price": actual_price,
                "greeks": {
                    "delta": 1.0,
                    "gamma": 0.0,
                    "theta": 0.0,
                    "vega": 0.0,
                    "iv": 0.0
                }
            },
            # Short Put leg
            {
                "symbol": short_sym,
                "underlying_symbol": ticker,
                "type": "put",
                "strike": short_strike,
                "expiration_date": exp_date,
                "quantity": -2,
                "price": short_opt["price"],
                "current_price": short_opt["price"],
                "greeks": short_opt["greeks"]
            },
            # Long Put leg
            {
                "symbol": long_sym,
                "underlying_symbol": ticker,
                "type": "put",
                "strike": long_strike,
                "expiration_date": exp_date,
                "quantity": 2,
                "price": long_opt["price"],
                "current_price": long_opt["price"],
                "greeks": long_opt["greeks"]
            }
        ]
        
    return {
        "price": actual_price,
        "current_price": actual_price,
        "ticker": ticker,
        "spy_200_sma": spy_200_sma,
        "reflection_count": state.get("reflection_count") or 0,
        "timestamp": timestamp,
        "option_chain": option_chain,
        "portfolio_inventory": portfolio_inventory,
        "cash": cash,
        "portfolio_equity": portfolio_equity,
        "margin_utilization": margin_utilization,
        "portfolio_greeks": state.get("portfolio_greeks", {"delta": 0.0, "gamma": 0.0, "theta": 0.0})
    }
