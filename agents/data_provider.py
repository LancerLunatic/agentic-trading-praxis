from core.state import AgentState
import alpaca_trade_api as tradeapi
import os
import math
import requests
import re
import pandas as pd
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

def data_provider_node(state: AgentState) -> dict:
    ticker = state.get("ticker")
    timestamp = state.get("timestamp")
    
    # Robust unpacking if ticker is passed as a list from LangGraph console
    if isinstance(ticker, list):
        if len(ticker) > 0:
            ticker = ticker[0]
        else:
            raise ValueError("Ticker list is empty!")
            
    if not ticker and state.get("portfolio_inventory"):
        for item in state["portfolio_inventory"]:
            if item.get("symbol"):
                ticker = item.get("symbol")
                break
                
    if ticker is None:
        raise ValueError("No ticker provided in the graph input state!")
        
    ticker = str(ticker).strip().upper()
    if not ticker:
        raise ValueError("Ticker is empty or invalid after normalization!")

    print(f"--- FETCHING DATA FOR: {ticker} (timestamp: {timestamp}) ---")

    # 1. Fetch current price of the underlying ticker
    actual_price = None
    if state.get("price") is not None:
        actual_price = float(state.get("price"))
    elif state.get("current_price") is not None:
        actual_price = float(state.get("current_price"))

    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    
    use_mock_data = False
    if not api_key or not secret_key or "your_alpaca" in api_key or "your_alpaca" in secret_key:
        use_mock_data = True
        print("=================================================================")
        print("  WARNING: USING MOCK / SIMULATED MARKET DATA & OPTION CHAINS")
        print("  Reason: Missing or invalid Alpaca API credentials.")
        print("=================================================================")
    
    if actual_price is None:
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
                
        if use_mock_data or actual_price is None:
            actual_price = 420.0

    print(f"--- SUCCESS: {ticker} price is ${actual_price:.2f} ---")

    # 2. Fetch/Compute SPY 200-day Simple Moving Average (SMA)
    spy_200_sma = 0.0
    spy_bars_df = None
    if not use_mock_data:
        try:
            from alpaca_trade_api.rest import TimeFrame
            if timestamp:
                spy_bars = api.get_bars("SPY", TimeFrame.Day, end=timestamp, limit=200).df
            else:
                spy_bars = api.get_bars("SPY", TimeFrame.Day, limit=200).df
                
            if not spy_bars.empty:
                spy_200_sma = float(spy_bars['close'].mean())
                spy_bars_df = spy_bars
            else:
                spy_200_sma = 0.0
        except Exception as e:
            print(f"Alpaca SPY SMA fetch failed: {e}.")
            
    if use_mock_data or spy_200_sma == 0.0:
        if state.get("spy_200_sma") is not None:
            spy_200_sma = float(state.get("spy_200_sma"))
        else:
            spy_200_sma = 450.0
            
        spy_bars_df = state.get("spy_bars")
        if spy_bars_df is None:
            dates = pd.date_range(end="2026-07-08", periods=200, freq='B')
            spy_bars_df = pd.DataFrame({'close': [400.0] * 200}, index=dates)

    print(f"--- SUCCESS: SPY 200-day SMA is ${spy_200_sma:.2f} ---")

    # 3. Ingestion SPY and XLU daily historical bars
    xlu_bars_df = None
    if not use_mock_data:
        try:
            from alpaca_trade_api.rest import TimeFrame
            if timestamp:
                xlu_bars = api.get_bars("XLU", TimeFrame.Day, end=timestamp, limit=200).df
            else:
                xlu_bars = api.get_bars("XLU", TimeFrame.Day, limit=200).df
                
            if not xlu_bars.empty:
                xlu_bars_df = xlu_bars
        except Exception as e:
            print(f"Alpaca XLU bars fetch failed: {e}.")
            
    if use_mock_data or xlu_bars_df is None:
        xlu_bars_df = state.get("xlu_bars")
        if xlu_bars_df is None:
            dates = pd.date_range(end="2026-07-08", periods=200, freq='B')
            xlu_bars_df = pd.DataFrame({'close': [60.0] * 200}, index=dates)

    # 4. Ingestion VIX price
    vix_price = state.get("vix_price")
    if vix_price is None:
        if not use_mock_data:
            try:
                latest_vix = api.get_latest_trade("VIX")
                vix_price = float(latest_vix.price)
            except Exception as e:
                print(f"Alpaca VIX fetch failed: {e}. Trying bars...")
                try:
                    from alpaca_trade_api.rest import TimeFrame
                    vix_bars = api.get_bars("VIX", TimeFrame.Day, limit=1).df
                    if not vix_bars.empty:
                        vix_price = float(vix_bars['close'].iloc[-1])
                except Exception as e2:
                    print(f"Alpaca VIX bars fetch failed: {e2}.")
                    
        if vix_price is None or vix_price == 0.0:
            vix_price = 15.0

    # 5. Candidate Selection (Dynamically select top 75 liquid equities)
    liquid_pool = [
        "AAPL", "MSFT", "TSLA", "NVDA", "AMZN", "NFLX", "META", "GOOGL", "GOOG", "AMD",
        "INTC", "MS", "GS", "JPM", "BAC", "WFC", "C", "COF", "AXP", "V",
        "MA", "PYPL", "SQ", "QQQ", "SPY", "IWM", "DIA", "XLE", "XLF", "XLK",
        "XLY", "XLP", "XLI", "XLU", "XLV", "XLB", "DIS", "UNH", "HD", "PG",
        "JNJ", "COST", "ABBV", "AVGO", "CRM", "MRK", "LLY", "PEP", "KO", "CVX",
        "XOM", "NKE", "ADBE", "MCD", "WMT", "CSCO", "ACN", "T", "VZ", "CMG",
        "PFE", "QCOM", "TXN", "AMAT", "LRCX", "MU", "NOW", "INTU", "ORCL", "IBM",
        "CAT", "GE", "PM", "UNP", "HON", "RTX", "BA", "LMT", "UPS", "FDX",
        "DE", "SBUX", "TGT", "LOW", "SPG", "TJX", "CVS", "SCHW", "BLK", "MDT",
        "EL", "PLTR", "UBER", "ABNB", "SNOW", "TSM", "BABA", "NIO", "PANW", "MRVL"
    ]
    
    screened_candidates = []
    ticker_volume_data = {}
    
    if use_mock_data:
        candidates_data = []
        for t in liquid_pool:
            t_hash = abs(hash(t))
            price = 2.50 + (t_hash % 34750) / 100.0  # guaranteed between 2.50 and 350.00
            volume = 100000 + (t_hash % 9900000)
            dollar_vol = price * volume
            candidates_data.append((t, price, dollar_vol))
        candidates_data.sort(key=lambda x: x[2], reverse=True)
        screened_candidates = [t for t, p, dv in candidates_data if 2.50 <= p <= 350.00][:75]
    else:
        try:
            from alpaca_trade_api.rest import TimeFrame
            if timestamp:
                bars_df = api.get_bars(liquid_pool, TimeFrame.Day, end=timestamp, limit=1).df
            else:
                bars_df = api.get_bars(liquid_pool, TimeFrame.Day, limit=1).df
            
            df_reset = bars_df.reset_index()
            has_symbol = False
            for col in ['symbol', 'level_0', 'index']:
                if col in df_reset.columns and df_reset[col].isin(liquid_pool).any():
                    has_symbol = col
                    break
            
            if has_symbol:
                for idx, row in df_reset.iterrows():
                    sym = str(row[has_symbol])
                    close = float(row['close'])
                    vol = float(row['volume']) if 'volume' in row else 1000000.0
                    ticker_volume_data[sym] = (close, vol)
            else:
                raise ValueError("Multi-symbol get_bars did not return symbol column (likely mock)")
        except Exception as e:
            ticker_volume_data = {}
            for t in liquid_pool:
                try:
                    from alpaca_trade_api.rest import TimeFrame
                    if timestamp:
                        t_bars = api.get_bars(t, TimeFrame.Day, end=timestamp, limit=1).df
                    else:
                        t_bars = api.get_bars(t, TimeFrame.Day, limit=1).df
                    if not t_bars.empty:
                        close = float(t_bars['close'].iloc[-1])
                        vol = float(t_bars['volume'].iloc[-1]) if 'volume' in t_bars.columns else 1000000.0
                        ticker_volume_data[t] = (close, vol)
                except Exception:
                    pass
        
        candidates_data = []
        for t in liquid_pool:
            if t in ticker_volume_data:
                close, vol = ticker_volume_data[t]
                dollar_vol = close * vol
                if 2.50 <= close <= 350.00:
                    candidates_data.append((t, dollar_vol))
        candidates_data.sort(key=lambda x: x[1], reverse=True)
        screened_candidates = [t for t, dv in candidates_data[:75]]

    # Ensure current ticker price bounds filter is strictly respected
    in_bounds = (2.50 <= actual_price <= 350.00)
    if in_bounds:
        if ticker not in screened_candidates:
            screened_candidates.append(ticker)
    else:
        screened_candidates = [t for t in screened_candidates if t != ticker]

    # 6. Fetch/Generate Option Chains for all screened candidates
    option_chain = {}
    if not use_mock_data:
        for t in screened_candidates:
            try:
                url = f"https://data.alpaca.markets/v1beta1/options/snapshots/{t}"
                headers = {
                    "APCA-API-KEY-ID": api_key,
                    "APCA-API-SECRET-KEY": secret_key,
                    "accept": "application/json"
                }
                response = requests.get(url, headers=headers, timeout=5)
                if response.status_code == 200:
                    res_data = response.json() or {}
                    snapshots = res_data.get("snapshots") or {}
                    for contract_symbol, snap in snapshots.items():
                        match = re.match(r"^([A-Z]+)(\d{6})([CP])(\d{8})$", contract_symbol)
                        if match:
                            und, date_part, cp, strike_part = match.groups()
                            expiration = f"20{date_part[0:2]}-{date_part[2:4]}-{date_part[4:6]}"
                            option_type = "call" if cp == "C" else "put"
                            strike = float(strike_part) / 1000.0
                        else:
                            continue
                            
                        greeks_data = snap.get("greeks") or {}
                        quote_data = snap.get("latestQuote") or {}
                        trade_data = snap.get("latestTrade") or {}
                        
                        price = float(trade_data.get("price") or quote_data.get("ask", 0.0) or 0.0)
                        
                        option_chain[contract_symbol] = {
                            "contract_symbol": contract_symbol,
                            "underlying_symbol": t,
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
                print(f"Alpaca Options API check failed for {t}: {e}. Will generate mock.")

    # Loop through all screened candidates to fill missing option chains using BS generator
    for t in screened_candidates:
        has_opts = any(opt["underlying_symbol"] == t for opt in option_chain.values())
        if not has_opts:
            t_price = actual_price if t == ticker else ticker_volume_data.get(t, (100.0, 0))[0]
            if not t_price or t_price <= 0:
                t_hash = abs(hash(t))
                t_price = 2.50 + (t_hash % 34750) / 100.0
                
            expirations = [("2026-07-17", 10/365), ("2026-08-07", 30/365)]
            
            if t_price <= 10.0:
                strikes = [float(k) for k in [t_price * factor for factor in [0.5, 0.8, 0.9, 1.0, 1.1, 1.2, 1.5]]]
                strikes = sorted(list(set(round(k * 2) / 2 for k in strikes)))
                strikes = [k for k in strikes if k > 0]
            else:
                strikes = [float(k) for k in range(int(t_price - 20), int(t_price + 25), 5)]
                strikes = [k for k in strikes if k > 0]
                
            for exp_date, T in expirations:
                for strike in strikes:
                    dist_pct = (t_price - strike) / t_price
                    iv = 0.20 + 0.15 * (dist_pct ** 2)
                    r = 0.045
                    
                    # Call option
                    c_price, c_delta, c_gamma, c_theta, c_vega = black_scholes_greeks(t_price, strike, T, r, iv, "call")
                    c_symbol = f"{t}{exp_date.replace('-','')[2:]}C{str(int(strike*1000)).zfill(8)}"
                    option_chain[c_symbol] = {
                        "contract_symbol": c_symbol,
                        "underlying_symbol": t,
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
                    p_price, p_delta, p_gamma, p_theta, p_vega = black_scholes_greeks(t_price, strike, T, r, iv, "put")
                    p_symbol = f"{t}{exp_date.replace('-','')[2:]}P{str(int(strike*1000)).zfill(8)}"
                    option_chain[p_symbol] = {
                        "contract_symbol": p_symbol,
                        "underlying_symbol": t,
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

    # 7. Initialize state parameters
    cash = state.get("cash", 100000.0)
    portfolio_equity = state.get("portfolio_equity", 100000.0)
    margin_utilization = state.get("margin_utilization", 0.0)
    
    portfolio_inventory = state.get("portfolio_inventory")
    if portfolio_inventory is None:
        portfolio_inventory = []
        
    return {
        "price": actual_price,
        "current_price": actual_price,
        "ticker": ticker,
        "spy_200_sma": spy_200_sma,
        "vix_price": vix_price,
        "spy_bars": spy_bars_df,
        "xlu_bars": xlu_bars_df,
        "screened_candidates": screened_candidates,
        "reflection_count": state.get("reflection_count") or 0,
        "timestamp": timestamp,
        "option_chain": option_chain,
        "portfolio_inventory": portfolio_inventory,
        "cash": cash,
        "portfolio_equity": portfolio_equity,
        "margin_utilization": margin_utilization,
        "portfolio_greeks": state.get("portfolio_greeks", {"delta": 0.0, "gamma": 0.0, "theta": 0.0})
    }
